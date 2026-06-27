"""School rating engine — Bayesian, zero-sum update over each contest's 校排.

The competitor is a **school**, and the rating is a Bayesian running mean of the
levels it has played at among schools — **not** the player ladder. Two properties
the player ladder lacks and the user wants:

* **Bayesian / stable.** The step toward a contest's performance uses a
  *decreasing* learning rate ``1 / (KAPPA + n)`` (the online posterior-mean update
  of a Normal mean with a ``KAPPA``-strength prior at ``MU0``). So a school's
  rating is its all-history average, and a single extreme contest barely moves a
  seasoned school — no over-reacting to the latest/wildest result.
* **Zero-sum.** After the steps, one uniform shift makes the contest's rating
  changes net to exactly 0 — points are redistributed, never inflated.

Per contest:

1. **School standing.** A school is its single strongest official team that
   contest — the smallest (best) rank among its ``official`` & participating
   rostered rows. Schools are ranked among themselves (1224 ties).
2. **Performance (校排 → perf).** Treat the participating schools as a field with
   their current ratings and feed that field + the school ranks to the shared
   Codeforces-style inversion (:func:`xcpc_rating.perf.compute_performances`):
   the level the school played at among schools (topping a strong, deep field is
   worth more).
3. **Bayesian zero-sum step.** With ``alpha_i = 1 / (KAPPA + n_i)`` (``n_i``
   counting this contest)::

       step_i = alpha_i * (perf_i - rating_i)     # online mean update (shrinks with n)
       inc    = -mean(step)                        # so Σ (step + inc) = 0
       rating_i += step_i + inc

   Performing above your rating rises, below it falls; a veteran moves little, a
   newcomer adapts fast; the field's net change is zero.

Everyone starts at ``MU0`` and the mean stays pinned there (zero-sum), strong
schools above and weak below on the same ~1400–3000 scale as players.
"""

from __future__ import annotations

from typing import NamedTuple

from .. import perf
from ..model import Contest
from ..tier import (
    TIER_FINAL,
    TIER_INVITATIONAL,
    TIER_PROVINCIAL,
    TIER_REGIONAL,
    classify_tier,
)

# Starting rating; the zero-sum update keeps the field mean pinned here.
MU0 = perf.INITIAL_RATING  # 1500.0
# Prior strength in pseudo-contests: sets the first-contest learning rate
# 1/(KAPPA+1) and how fast the rating stabilizes (larger → steadier, more shrunk).
KAPPA = 4.0
# Per-contest prestige weight on a school's rating change, relative to an ordinary
# regional (the 1.0 baseline). A Final (EC / World / CCPC final — id ``...ecfinal``
# / title 总决赛) moves a rating 1.5× as far; invitationals 0.8× and provincials
# 0.5× (lower-prestige, weaker fields — they barely shift a rating). Scales the
# step both up and down, so a Final separates schools faster than a 省赛.
SCHOOL_TIER_WEIGHTS = {
    TIER_FINAL: 1.5,
    TIER_REGIONAL: 1.0,
    TIER_INVITATIONAL: 0.8,
    TIER_PROVINCIAL: 0.5,
}
# Performance cap: a school can prove at most this far above the strongest *other*
# school present. Beating a weak field can't manufacture a sky-high performance,
# so two strong schools sharing a weak provincial land close together instead of
# being split by the raw rank-1-vs-rank-2 gap. Larger → caps less (raw cf-pure).
PERF_CAP_MARGIN = 200.0


def school_standings(contest: Contest) -> dict[str, int]:
    """Map each participating school to its best (smallest) official team rank.

    Only ``official`` & ``participated`` rostered teams count; a team's school is
    its members' shared org (the loader assigns every member of a row the row's
    organization). Teams with an empty org or no roster are ignored. A school that
    fielded several teams keeps its strongest result.
    """
    best: dict[str, int] = {}
    for team in contest.teams:
        if not (team.official and team.participated and team.members):
            continue
        org = team.members[0].org
        if not org or not org.strip():
            continue
        if org not in best or team.rank < best[org]:
            best[org] = team.rank
    return best


def rank_among_schools(best_ranks: list[int]) -> list[int]:
    """1224 competition ranks over per-school best-team ranks (smaller = better).

    Two schools whose best teams tied on contest rank share a school rank. The
    result is aligned to the input order, so it pairs with the schools' rating
    list for the performance solve.
    """
    order = sorted(range(len(best_ranks)), key=lambda i: best_ranks[i])
    ranks = [0] * len(best_ranks)
    prev_value = None
    current = 0
    for position, idx in enumerate(order):
        value = best_ranks[idx]
        if prev_value is None or value != prev_value:
            current = position + 1
        ranks[idx] = current
        prev_value = value
    return ranks


def cap_performances(
    performances: list[float],
    field: list[float],
    ranks: list[int],
    margin: float = PERF_CAP_MARGIN,
) -> list[float]:
    """Cap raw performances at "strongest other school present + margin".

    Beating a weak field can't prove a level far above the field, so the champion
    of a top-heavy provincial doesn't get a runaway performance. Each school is
    capped at the strongest *other* school's rating plus ``margin`` (the champion's
    cap is the runner-up's rating; everyone else's is the champion's). A final
    pass enforces non-increasing performance by rank so the cap can never invert
    the standings (a worse rank ending above a better one).
    """
    n = len(field)
    i_max = max(range(n), key=lambda i: field[i])
    top = field[i_max]
    runner_up = max((field[j] for j in range(n) if j != i_max), default=top)
    capped = [
        min(performances[i], (runner_up if i == i_max else top) + margin)
        for i in range(n)
    ]
    # Walk best-rank-first, holding a running ceiling so perf never rises with rank.
    running = float("inf")
    for i in sorted(range(n), key=lambda i: ranks[i]):
        running = min(running, capped[i])
        capped[i] = running
    return capped


class SchoolStanding(NamedTuple):
    """One school's row on the leaderboard."""

    org: str
    rating: float
    contests: int


class SchoolResult(NamedTuple):
    """One school's result in one contest (a row of the 学校成绩 history)."""

    org: str
    team_rank: int      # best official team's rank among all teams
    school_rank: int    # this school's rank among schools (1224)
    school_count: int   # number of schools in the contest
    perf: float         # the school's performance this contest


class SchoolEngine:
    """Accumulates each school's Bayesian zero-sum rating across contests."""

    def __init__(
        self,
        mu0: float = MU0,
        kappa: float = KAPPA,
        tier_weights: dict | None = None,
    ) -> None:
        self.mu0 = mu0
        self.kappa = kappa
        self.tier_weights = tier_weights if tier_weights is not None else SCHOOL_TIER_WEIGHTS
        # org -> {"rating": float, "contests": int}
        self._schools: dict[str, dict] = {}

    def prior_rating(self) -> float:
        """The rating a school carries before any contest."""
        return self.mu0

    def rating(self, org: str) -> float:
        """Current rating for one school."""
        return self._schools[org]["rating"]

    def _rating(self, org: str) -> float:
        """Pre-contest field rating; a never-seen school sits at the prior."""
        state = self._schools.get(org)
        return self.mu0 if state is None else state["rating"]

    def score_contest(self, contest: Contest) -> list[SchoolResult]:
        """Apply one contest's Bayesian zero-sum update; return per-school results.

        A contest with fewer than two schools has no field to measure a
        performance against and is skipped (returns ``[]``). Performances use the
        *pre-contest* field ratings (no look-ahead). The learning rate decreases
        with each school's contest count (stable, Bayesian) and the per-school
        rating changes sum to exactly zero across the contest.
        """
        standings = school_standings(contest)
        if len(standings) < 2:
            return []

        orgs = list(standings.keys())
        best_team_ranks = [standings[org] for org in orgs]
        field = [self._rating(org) for org in orgs]
        ranks = rank_among_schools(best_team_ranks)
        performances = cap_performances(
            list(perf.compute_performances(field, ranks)), field, ranks
        )

        # Prestige weight: a Final moves ratings 1.5× as far as a regional.
        weight = self.tier_weights.get(classify_tier(contest), 1.0)

        # Online posterior-mean step with a per-school decreasing learning rate:
        # alpha = 1/(KAPPA + n) where n counts this contest. A seasoned school
        # (large n) barely moves; a newcomer adapts fast.
        steps = []
        for org, performance, level in zip(orgs, performances, field):
            n_after = self._schools.get(org, {}).get("contests", 0) + 1
            alpha = 1.0 / (self.kappa + n_after)
            steps.append(weight * alpha * (float(performance) - level))
        # Uniform shift so the contest's rating changes net to zero (no inflation).
        inc = -sum(steps) / len(steps)

        results: list[SchoolResult] = []
        school_count = len(orgs)
        for org, performance, school_rank, team_rank, level, step in zip(
            orgs, performances, ranks, best_team_ranks, field, steps
        ):
            state = self._schools.setdefault(org, {"rating": self.mu0, "contests": 0})
            state["rating"] = level + step + inc
            state["contests"] += 1
            results.append(
                SchoolResult(org, team_rank, school_rank, school_count, float(performance))
            )
        return results

    def process_contest(self, contest: Contest) -> None:
        """Apply one contest's Bayesian zero-sum update to every participating school."""
        self.score_contest(contest)

    def leaderboard(self, min_contests: int = 1) -> list[SchoolStanding]:
        """All schools with ``>= min_contests`` games, ordered by rating desc.

        Ties on the (full-precision) rating fall back to the org name so the order
        is deterministic across runs.
        """
        rows = [
            SchoolStanding(org, state["rating"], state["contests"])
            for org, state in self._schools.items()
            if state["contests"] >= min_contests
        ]
        rows.sort(key=lambda row: (-row.rating, row.org))
        return rows
