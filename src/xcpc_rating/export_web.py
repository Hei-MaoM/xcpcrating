"""Static web data exporter for the xcpc-rating data site.

This module turns the incremental-ladder pipeline (``xcpc_rating.engines.
incremental`` -- the single scoring rule, "从 0 起步逐场累积") into the static
JSON bundle the Vite/React frontend consumes. It does **not** touch the scoring
rule: it replays the exact same time-ordered backtest the validator runs,
snapshots per-contest predictions/performances without look-ahead leakage, and
writes the single-board data contract the frontend's ``web/src/lib/data.ts``
mirrors.

Run as a module::

    python -m xcpc_rating.export_web \
        --data vendor/srk-collection/official \
        --out  web/public/data

Pipeline, per contest in chronological order (same order the loader guarantees):

1. **Predict before update (no leakage).** Take the engine's ``predict_scores``
   on the pre-update state, derive a 1-based ``predictedRank`` per team (higher
   score = better = lower rank, stable sort), and the per-contest pairwise
   ``concordance`` via the shared validator function.
2. **Process the contest.** Update the engine's internal state.
3. **Snapshot performances.** The engine appended one raw internal-track perf
   sample per real member (rank-1 teams carry the redefined champion solve); a
   team's perf is read back from any real member's history tail (all members of
   a team share it). Ghost teams (no roster) persist nothing -> ``perf = null``.
4. **Record per-member history rows.** ``rating_after`` is the member's display
   ladder score after this contest; ``mu_after`` is the internal expectation E.

After the full replay the terminal engine state plus the accumulated per-contest
and per-player aggregates are written out as the contract files. JSON is emitted
compact (no spaces); the player index is the array-compressed form; player detail
files are sharded into 256 buckets by the first two hex chars of ``md5(key)``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone

from . import perf
from .engines.incremental import INITIAL_EXPECT as PRIOR_MU
from .engines.incremental import (
    UNRATED_CONTESTS,
    IncrementalEngine,
    display_score,
    rerank_1224,
)
from .identity import clean_org, display_name, resolve_i18n
from .loader import SRK_SUFFIX, load_contests
from .medals import MEDAL_COLORS, collect_medals
from .validate import pairwise_concordance

# Single scoring engine: the incremental ladder (see the README, 评分算法).
# Engine names are never shown in the UI; this string only stamps the meta.json
# provenance field.
ENGINE = "incremental"

# A player must have at least this many rated contests to carry a display rating
# and to appear on the leaderboard. A single rated contest is enough (a score
# after one contest); only a player with 0 rated contests carries a null rating.
MIN_RATED_CONTESTS = 1

# Player detail files are sharded into 256 buckets by md5(key)[:2].
SHARD_HEX_LEN = 2

# Default I/O, resolved relative to the repo root (this file lives at
# src/xcpc_rating/export_web.py). Source data is a git submodule
# (vendor/srk-collection); update it via scripts/update_data.sh.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_DATA = os.path.join(_REPO_ROOT, "vendor", "srk-collection", "official")
DEFAULT_OUT = os.path.join(_REPO_ROOT, "web", "public", "data")

# Numeric rounding for compact, stable JSON (ratings/perf to 2 dp).
_ROUND_DP = 2

# Penalty time-unit normalization to whole minutes. The raw srk ``score.time`` is
# a ``[value, unit]`` pair whose unit varies across boards (seconds, milliseconds,
# or already minutes); the loader keeps only the bare value, so the unit is read
# back here from the raw row. Each unit's value is converted to minutes and
# floored to a whole minute for a single comparable penalty scale on the site.
_PENALTY_MINUTE_DIVISOR = {
    "s": 60.0,
    "ms": 60000.0,
    "min": 1.0,
}


# --------------------------------------------------------------------------- #
# Small pure helpers
# --------------------------------------------------------------------------- #


def contest_slug(contest_id: str) -> str:
    """Map a contest id to a filesystem-safe slug (``'/'`` -> ``'__'``)."""
    return contest_id.replace("/", "__")


def player_shard(key: str) -> str:
    """Return the 2-hex-char shard bucket for a player key (md5 prefix)."""
    digest = hashlib.md5(key.encode("utf-8")).hexdigest()
    return digest[:SHARD_HEX_LEN]


def _round(value):
    """Round floats to the contract precision; pass other values through."""
    if isinstance(value, float):
        return round(value, _ROUND_DP)
    return value


def predicted_ranks(scores: list[float]) -> list[int]:
    """1-based competition-style ranks from predicted scores (higher = better).

    A stable descending sort: the strongest predicted team is rank 1. Ties get
    the standard "1224" minimum rank so two equally-predicted teams share a rank.
    The result is aligned to the input team order.
    """
    n = len(scores)
    # Stable sort of team indices by descending score (mergesort-style stable).
    order = sorted(range(n), key=lambda i: (-scores[i], i))
    ranks = [0] * n
    prev_score = None
    current_rank = 0
    for position, team_index in enumerate(order):
        score = scores[team_index]
        if prev_score is None or score != prev_score:
            current_rank = position + 1
        ranks[team_index] = current_rank
        prev_score = score
    return ranks


# --------------------------------------------------------------------------- #
# Raw team-name recovery
# --------------------------------------------------------------------------- #


def _raw_team_rows(data_root: str, contest_id: str) -> list[dict]:
    """Re-read a contest's raw srk.json rows to recover team display fields.

    The loader keeps a 1:1 row->team mapping in standings order but discards the
    team's display name / org (it only persists members). We re-read the source
    file purely to recover ``name`` / ``org`` for the contest detail view; the
    rows are returned positionally aligned with ``Contest.teams``.
    """
    path = os.path.join(data_root, contest_id + SRK_SUFFIX)
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    return data.get("rows", []) or []


def _penalty_minutes(raw_row: dict) -> int:
    """Normalize a raw srk row's ``score.time`` penalty to whole minutes.

    ``score.time`` is a ``[value, unit]`` pair; the unit (``"s"`` / ``"ms"`` /
    ``"min"``) is divided into minutes (s/60, ms/60000, min unchanged) and the
    result is floored to a whole minute. A bare number, a missing time, or an
    unrecognized unit falls back to flooring the raw value as-is (best effort, so
    a data drift never crashes the export). Returns an ``int`` minute count.
    """
    score = raw_row.get("score", {}) or {}
    time = score.get("time")
    if isinstance(time, (list, tuple)):
        value = time[0] if time else 0
        unit = time[1] if len(time) > 1 else None
    else:
        value, unit = time, None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return 0
    divisor = _PENALTY_MINUTE_DIVISOR.get(str(unit).lower(), 1.0)
    # Penalty is non-negative, so int() truncation is the floor toward zero.
    return int(value / divisor)


def _team_display(raw_row: dict) -> tuple[str, str]:
    """Recover a team's display ``(name, org)`` from a raw srk row.

    The team name is cleaned the same way member display names are (bracketed
    segments stripped, whitespace folded); org uses the shared org cleaner.
    """
    user = raw_row.get("user", {}) or {}
    name = display_name(user.get("name")) or resolve_i18n(user.get("name"))
    org = clean_org(user.get("organization"))
    return name, org


# --------------------------------------------------------------------------- #
# Per-player accumulator
# --------------------------------------------------------------------------- #


class _PlayerAcc:
    """Accumulates a single player's identity and per-contest history rows."""

    __slots__ = ("key", "name", "org", "history")

    def __init__(self, key: str, name: str, org: str) -> None:
        self.key = key
        self.name = name
        self.org = org
        self.history: list[dict] = []


def _perf_tail(engine: IncrementalEngine, member_key: str):
    """The ladder engine's just-recorded performance for a member, or ``None``.

    Called immediately after ``engine.process_contest``, so ``last_perf`` is
    exactly this contest's recovered performance (rank-1 teams carry the
    champion solve). Reading it back keeps the exported perf byte-identical to
    what the engine actually stepped toward -- the same口径 as the 变化 column.
    """
    state = engine._players.get(member_key)  # noqa: SLF001 - read-only snapshot
    if state is None:
        return None
    return state["last_perf"]


def _display_state(engine: IncrementalEngine, member_key: str):
    """Ladder ``(display, expect, contests)`` for a member, or ``None``.

    ``display`` is the user-facing score, which is the raw expectation ``E``
    itself (everyone starts at 1400); ``expect`` is that same internal ``E``.
    """
    state = engine._players.get(member_key)  # noqa: SLF001 - read-only snapshot
    if state is None:
        return None
    return (
        display_score(state["expect"], state["contests"]),
        state["expect"],
        state["contests"],
    )


def _member_mu(engine: IncrementalEngine, member_key: str):
    """Ladder expectation ``E`` for a member, or ``None`` if unseen.

    The pre-contest team rating shown on the detail view (``preRating``) is the
    LSE of members' expectations, matching the engine's own team-strength /
    prediction口径.
    """
    state = engine._players.get(member_key)  # noqa: SLF001 - read-only snapshot
    return state["expect"] if state is not None else None


def _team_pre_rating(engine: IncrementalEngine, team) -> float | None:
    """Pre-contest team rating: LSE of members' pre-update expectations ``E``.

    Returns ``None`` for a ghost team (no roster). Members unseen before this
    contest fall back to the initial expectation (the same value the engine
    itself would seed them at), so a team of brand-new players reports the
    initial LSE rather than ``None``.
    """
    if not team.members:
        return None
    mus = [
        mu if (mu := _member_mu(engine, m.key)) is not None
        else PRIOR_MU
        for m in team.members
    ]
    return perf.lse_aggregate(mus)


def _team_mu_delta(
    engine: IncrementalEngine, team, pre_member_expect: dict[str, float]
) -> float | None:
    """Average change in members' internal expectation ``E`` across this contest.

    ``pre_member_expect`` maps member key -> that member's pre-update expectation
    ``E`` (INITIAL_EXPECT for never-seen players). The post-update ``E`` is read
    back from the engine after it processed the contest, so the 变化 column is the
    team's real internal movement (display == ``E``, so this is also the displayed
    change). A member gated out of the contest keeps the same ``E`` and so
    contributes 0. Returns the mean per-member delta, or ``None`` for a ghost team
    (no roster).
    """
    if not team.members:
        return None
    deltas = []
    for member in team.members:
        state = engine._players.get(member.key)  # noqa: SLF001 - snapshot
        if state is None:
            continue
        post = state["expect"]
        pre = pre_member_expect.get(member.key, PRIOR_MU)
        deltas.append(post - pre)
    if not deltas:
        return None
    return sum(deltas) / len(deltas)


# --------------------------------------------------------------------------- #
# Replay
# --------------------------------------------------------------------------- #


def _isoformat(dt: datetime) -> str:
    """ISO-8601 string for a contest start time (preserves offset if present)."""
    return dt.isoformat()


def replay_and_collect(contests, data_root: str):
    """Time-ordered replay collecting everything the contract files need.

    Returns ``(contest_docs, players, engine)`` where ``contest_docs`` is the
    per-contest detail list (in chronological order) and ``players`` maps key ->
    _PlayerAcc. The engine is driven exactly like the validator: predict
    (pre-update), then process, with no look-ahead leakage.
    """
    engine = IncrementalEngine()

    contest_docs: list[dict] = []
    players: dict[str, _PlayerAcc] = {}

    for contest in contests:
        slug = contest_slug(contest.id)
        ranks = [team.rank for team in contest.teams]

        # 1) Predict before update -> predictedRank + concordance (no leakage).
        scores = engine.predict_scores(contest)
        pred_rank = predicted_ranks(scores)
        conc = pairwise_concordance(scores, ranks)

        # Recover team display names (positionally aligned with teams).
        raw_rows = _raw_team_rows(data_root, contest.id)

        # Snapshot every member's pre-update internal expectation ``E`` (before
        # processing) so the per-team muDelta (post - pre mean of ``E``) can be
        # computed without look-ahead leakage. Unseen players fall back to the
        # engine's seed expectation (INITIAL_EXPECT), so their first contest
        # reports the real ``E`` step rather than the display "unlock".
        pre_member_expect: dict[str, float] = {}
        # Pre-contest rated-contest count per member, so a history row can record
        # whether this contest actually counted (a gated-out / display-only row is
        # unrated and renders its score columns as "—").
        pre_contests: dict[str, int] = {}
        for team in contest.teams:
            for member in team.members:
                mu = _member_mu(engine, member.key)
                pre_member_expect[member.key] = (
                    mu if mu is not None else PRIOR_MU
                )
                state = engine._players.get(member.key)  # noqa: SLF001
                pre_contests[member.key] = state["contests"] if state else 0

        # Pre-contest team rating (LSE of pre-update member mu), captured before
        # processing so it reflects the team's strength going in.
        pre_team_rating = [
            _team_pre_rating(engine, team) for team in contest.teams
        ]

        # 2) Update the engine.
        engine.process_contest(contest)

        # 3+4) Snapshot per-team perf and per-member history rows.
        team_docs = []
        for idx, team in enumerate(contest.teams):
            raw_row = raw_rows[idx] if idx < len(raw_rows) else {}
            team_name, team_org = _team_display(raw_row)

            # A non-participated team (0 submissions) is *displayed* in the
            # contest detail but is not a scoring row -- the engine never scored
            # it, so its perf / preRating / muDelta / predictedRank are null, and
            # its members get no history row (their contest count is unchanged,
            # "as if they never came"). member_docs is still emitted for all rows
            # so the standings render in full.
            participated = getattr(team, "participated", True)

            # A team's perf is shared by all its real members; ghost team -> None.
            # Ladder口径 (this contest's recovered performance, champion solve
            # for rank-1 teams) so the perf and 变化 columns agree.
            team_perf = None
            if participated and team.members:
                team_perf = _perf_tail(engine, team.members[0].key)

            member_docs = []
            for member in team.members:
                member_docs.append({"key": member.key, "name": member.display_name})

                if not participated:
                    # No belief sample, no history row, no contest count for a
                    # member who did not actually compete.
                    continue

                acc = players.get(member.key)
                if acc is None:
                    acc = _PlayerAcc(member.key, member.display_name, member.org)
                    players[member.key] = acc
                # Keep the most recent display name / org for the player.
                acc.name = member.display_name
                acc.org = member.org

                state = _display_state(engine, member.key)
                # rating_after = displayed ladder score (the 赛后分 column);
                # mu_after = internal expectation E (the chart's smooth μ line).
                rating_after = state[0] if state else None
                mu_after = state[1] if state else None
                member_perf = _perf_tail(engine, member.key)
                # Whether this contest counted toward the ladder for this member
                # (rated-contest count advanced). A gated-out row is unrated.
                rated = bool(state) and state[2] > pre_contests.get(member.key, 0)

                acc.history.append(
                    {
                        "contestId": slug,
                        "title": contest.title,
                        "startAt": _isoformat(contest.start_at),
                        "teamName": team_name,
                        "rank": team.rank,
                        "teamCount": len(contest.teams),
                        # Official ranking flag (false = 打星/非正式). Drives the
                        # player page's 正式参赛 view: a starred row is still shown
                        # but its score columns render "—".
                        "official": bool(team.official),
                        # Whether the contest counted toward the ladder; an unrated
                        # (gated-out) row renders its score columns as "—".
                        "rated": rated,
                        "perf": _round(member_perf) if member_perf is not None else None,
                        "rating_after": _round(rating_after)
                        if rating_after is not None
                        else None,
                        "mu_after": _round(mu_after) if mu_after is not None else None,
                    }
                )

            # Pre-contest team rating and this contest's mean E change. Ghost
            # teams (no roster) carry null for both (no belief to read). A
            # non-participated team carries null for the predicted rank, perf,
            # preRating and muDelta -- it was never scored.
            if participated:
                pre_rating = pre_team_rating[idx]
                mu_delta = _team_mu_delta(engine, team, pre_member_expect)
                predicted_rank = pred_rank[idx]
            else:
                pre_rating = None
                mu_delta = None
                predicted_rank = None

            team_docs.append(
                {
                    "rank": team.rank,
                    "name": team_name,
                    "org": team_org,
                    "solved": team.solved,
                    "penalty": _penalty_minutes(raw_row),
                    "official": team.official,
                    "members": member_docs,
                    "predictedRank": predicted_rank,
                    "perf": _round(team_perf) if team_perf is not None else None,
                    "preRating": _round(pre_rating) if pre_rating is not None else None,
                    "muDelta": _round(mu_delta) if mu_delta is not None else None,
                }
            )

        # Champion = the best official team's display name/org (fallback: rank 1).
        champion = _champion(team_docs)

        contest_docs.append(
            {
                "id": contest.id,
                "slug": slug,
                "title": contest.title,
                "startAt": _isoformat(contest.start_at),
                "category": contest.category,
                "teamCount": len(contest.teams),
                "concordance": _round(conc) if conc is not None else None,
                "unrated": contest.id in UNRATED_CONTESTS,
                "unratedNote": UNRATED_CONTESTS.get(contest.id),
                "teams": team_docs,
                "_champion": champion,
            }
        )

    return contest_docs, players, engine


def replay_official(contests):
    """Official-only replay: board, per-player rows, and per-contest team docs.

    Runs the engine with ``official_only=True`` so 打星 / official:false teams are
    absent from the field entirely (no rank, no score, no influence). Produces
    everything the 正式参赛 口径 needs, all computed over the official subset:

    * ``history[key][slug]`` -- per member: this contest's recovered perf,
      post-contest display rating / internal E, rank among official teams (1224
      over the official subset), official team count, and whether it counted
      (``rated``; a gated-out row is unrated).
    * ``contest_teams[slug][team_index]`` -- per official team: ``predictedRank``
      (1224 over official strengths), ``perf``, ``preRating``, ``muDelta``, and
      ``rank`` (among official teams), so the contest page can render the
      official-only standings / predictions.

    Returns ``(history, contest_teams, engine)``; ``engine`` is the terminal
    official engine (for the board).
    """
    engine = IncrementalEngine(official_only=True)
    history: dict[str, dict[str, dict]] = {}
    contest_teams: dict[str, dict[int, dict]] = {}
    for contest in contests:
        slug = contest_slug(contest.id)
        # Official subset (in standings order) and its indices in the full board.
        official_idx = [
            i for i, team in enumerate(contest.teams)
            if engine._counts(team)  # noqa: SLF001
        ]
        counted = [contest.teams[i] for i in official_idx]

        # Predict before update: strengths of the official teams, then 1224 ranks
        # among them (the predicted rank "among official teams").
        scores = engine.predict_scores(contest)
        official_scores = [scores[i] for i in official_idx]
        pred_official = predicted_ranks(official_scores)
        official_ranks = rerank_1224(counted)
        official_count = len(counted)

        # Pre-update snapshots over the official members (for muDelta / rated).
        pre_member_expect: dict[str, float] = {}
        pre_contests: dict[str, int] = {}
        for team in counted:
            for member in team.members:
                mu = _member_mu(engine, member.key)
                pre_member_expect[member.key] = mu if mu is not None else PRIOR_MU
                st = engine._players.get(member.key)  # noqa: SLF001
                pre_contests[member.key] = st["contests"] if st else 0
        pre_team_rating = [_team_pre_rating(engine, team) for team in counted]

        engine.process_contest(contest)

        team_map: dict[int, dict] = {}
        for j, team in enumerate(counted):
            i = official_idx[j]
            team_perf = _perf_tail(engine, team.members[0].key) if team.members else None
            mu_delta = _team_mu_delta(engine, team, pre_member_expect)
            pre_rating = pre_team_rating[j]
            team_map[i] = {
                "predictedRank": pred_official[j],
                "perf": _round(team_perf) if team_perf is not None else None,
                "preRating": _round(pre_rating) if pre_rating is not None else None,
                "muDelta": _round(mu_delta) if mu_delta is not None else None,
                "rank": official_ranks[j],
            }
            for member in team.members:
                disp = _display_state(engine, member.key)
                if disp is None:
                    continue
                member_perf = _perf_tail(engine, member.key)
                st = engine._players.get(member.key)  # noqa: SLF001
                rated = bool(st) and st["contests"] > pre_contests.get(member.key, 0)
                history.setdefault(member.key, {})[slug] = {
                    "perf": _round(member_perf) if member_perf is not None else None,
                    "rating_after": _round(disp[0]),
                    "mu_after": _round(disp[1]),
                    "rank": official_ranks[j],
                    "team_count": official_count,
                    "rated": rated,
                }
        contest_teams[slug] = team_map
    return history, contest_teams, engine


def _champion(team_docs: list[dict]) -> dict:
    """Pick the contest champion: the best-ranked official team (rank ascending).

    Falls back to the first team if none are flagged official. Returns a compact
    ``{name, org}`` record for the contests index.
    """
    best = None
    for team in team_docs:
        if not team["official"]:
            continue
        if best is None or team["rank"] < best["rank"]:
            best = team
    if best is None and team_docs:
        best = min(team_docs, key=lambda t: t["rank"])
    if best is None:
        return {"name": "", "org": ""}
    return {"name": best["name"], "org": best["org"]}


# --------------------------------------------------------------------------- #
# Terminal-state derivations (ratings, leaderboard, index)
# --------------------------------------------------------------------------- #


def _final_state(engine: IncrementalEngine, key: str):
    """Terminal ladder ``(rating, expect, contests)`` or ``None`` if unseen.

    ``rating`` is the displayed ladder score; ``expect`` is the internal
    expectation E (kept only for diagnostics, not exported).
    """
    state = engine._players.get(key)  # noqa: SLF001 - read-only snapshot
    if state is None:
        return None
    contests = state["contests"]
    rating = display_score(state["expect"], contests)
    return rating, state["expect"], contests


def _compact_medals(per_tier) -> dict:
    """Drop zero-medal tiers from one player's ``{tier: {gold,silver,bronze}}``.

    :func:`xcpc_rating.medals.collect_medals` returns a uniform all-tier shape
    (every tier present, zeros included). For the web contract we omit any tier
    where all three colors are zero, and omit the ``medals`` field entirely when
    the player earned nothing. The kept tiers retain the full
    ``{gold, silver, bronze}`` triple so the UI can render a stable row shape.
    Returns ``{}`` when the player has no medals (caller omits the field).
    """
    if not per_tier:
        return {}
    compact: dict[str, dict] = {}
    for tier, counts in per_tier.items():
        if any(counts.get(color, 0) for color in MEDAL_COLORS):
            compact[tier] = {color: int(counts.get(color, 0)) for color in MEDAL_COLORS}
    return compact


def build_player_records(players, engine, medals=None, official_history=None):
    """Build the full per-player detail records (terminal state + history).

    ``rating`` is ``None`` for players below the ``MIN_RATED_CONTESTS`` gate.
    Returns a dict key -> record.

    ``medals`` is the optional ``{key: {tier: {gold,silver,bronze}}}`` tally from
    :func:`xcpc_rating.medals.collect_medals`. When supplied, a player who earned
    at least one medal carries a ``medals`` field holding only the tiers where
    they medaled (zero-medal tiers are dropped); players with no medals omit the
    field entirely. When ``medals`` is ``None`` the field is never emitted.

    ``official_history`` is the optional ``{key: {slug: {perf, rating_after,
    mu_after, rank, team_count, rated}}}`` map from :func:`replay_official`. When
    supplied, each history row gains ``perfOfficial`` / ``ratingAfterOfficial`` /
    ``muAfterOfficial`` / ``rankOfficial`` / ``teamCountOfficial`` /
    ``ratedOfficial`` (null/false for a 打星 appearance with no official row), so
    the player page's 正式参赛 view can render the official-only trajectory and the
    rank-among-official-teams name次.
    """
    medals = medals or {}
    official_history = official_history or {}
    records: dict[str, dict] = {}
    for key, acc in players.items():
        contests = len(acc.history)
        state = _final_state(engine, key)
        rated = contests >= MIN_RATED_CONTESTS

        if state is not None and rated:
            rating = _round(state[0])
        else:
            rating = None

        # Merge in the official-only replay's per-contest perf/rating. A starred
        # contest has no official row -> the *Official fields stay null.
        off = official_history.get(key, {})
        history = []
        for row in acc.history:
            o = off.get(row["contestId"])
            history.append(
                {
                    **row,
                    "perfOfficial": o["perf"] if o else None,
                    "ratingAfterOfficial": o["rating_after"] if o else None,
                    "muAfterOfficial": o["mu_after"] if o else None,
                    "rankOfficial": o["rank"] if o else None,
                    "teamCountOfficial": o["team_count"] if o else None,
                    "ratedOfficial": o["rated"] if o else False,
                }
            )

        record = {
            "key": key,
            "name": acc.name,
            "org": acc.org,
            "contests": contests,
            "rating": rating,
            "history": history,
        }
        # Per-tier medal tally (gold/silver/bronze), zero-medal tiers omitted.
        # Field is present only for players who earned at least one medal so the
        # contract stays minimal and the players-index is untouched.
        compact = _compact_medals(medals.get(key))
        if compact:
            record["medals"] = compact
        records[key] = record
    return records


def build_players_index(records) -> list[list]:
    """Compact array-of-arrays index.

    Row form: ``[key, name, org, contests, rating]``. Sorted by descending
    rating (the default browse order), null ratings last, with key as a stable
    tiebreaker.
    """
    rows = [
        [
            r["key"],
            r["name"],
            r["org"],
            r["contests"],
            r["rating"],
        ]
        for r in records.values()
    ]
    # Sort by descending rating; None sinks to the bottom. (-inf sort key for
    # null ratings keeps them last while a stable key tiebreaker stays stable.)
    rows.sort(key=lambda row: (-(row[4] if row[4] is not None else float("-inf")), row[0]))
    return rows


def _yyyymmdd(iso: str) -> int:
    """Compact integer date ``YYYYMMDD`` from an ISO start-time string.

    The raw value looks like ``2024-05-12T09:00:00+08:00``; only the leading
    ``YYYY-MM-DD`` is kept and the dashes dropped, giving a chronologically
    sortable integer the frontend can range-compare without parsing dates.
    """
    return int(iso[:10].replace("-", ""))


def build_period_index(records) -> list[list]:
    """Per-player official-participation timeline for the 时间段 (period) board.

    The period board answers "who officially competed inside [from, to], and
    what was their official rating at the end of that window". Both questions are
    served by a single compact timeline per player: only **official**
    participations (rows with a non-null ``ratingAfterOfficial`` — a 打星/非正式
    appearance has none) are kept, as two parallel arrays in chronological order:

    * ``dates``   — ``YYYYMMDD`` ints (ascending; the contest dates)
    * ``ratings`` — the official-board display rating *after* each of those
      contests, rounded to one decimal to match the site's ``formatScore``.

    Row form: ``[key, name, org, dates, ratings]``. Players with zero official
    participations are omitted entirely (they can never appear on this board).
    The file is loaded lazily, only when the 时间段 tab is opened.
    """
    rows: list[list] = []
    for record in records.values():
        dates: list[int] = []
        ratings: list[float] = []
        for row in record["history"]:
            rating_official = row.get("ratingAfterOfficial")
            if rating_official is None:
                continue
            dates.append(_yyyymmdd(row["startAt"]))
            ratings.append(round(rating_official, 1))
        if not dates:
            continue
        rows.append([record["key"], record["name"], record["org"], dates, ratings])
    return rows


def build_leaderboard(engine, min_contests=MIN_RATED_CONTESTS):
    """Build the ladder leaderboard from the engine's own ``leaderboard``.

    This reuses the engine's leaderboard output directly (no re-derivation), so
    the board is exactly what the CLI/report would produce. ``rating`` is the
    displayed ladder score.
    """
    board = []
    for player in engine.leaderboard(min_contests=min_contests):
        board.append(
            {
                "key": player.key,
                "name": player.display_name,
                "org": player.org,
                "rating": _round(player.rating),
                "contests": player.contests,
            }
        )
    return board


# --------------------------------------------------------------------------- #
# Writers
# --------------------------------------------------------------------------- #


def _dump_json(path: str, obj) -> int:
    """Write ``obj`` as compact UTF-8 JSON; return the byte size written."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    data = text.encode("utf-8")
    with open(path, "wb") as handle:
        handle.write(data)
    return len(data)


def write_bundle(out_dir, contest_docs, records, engine, official_board=None):
    """Write the entire contract bundle under ``out_dir``. Returns file count.

    ``official_board`` is the optional second leaderboard (only-official-
    participation replay); when provided it is written to
    ``leaderboard_official.json`` alongside the main board.
    """
    os.makedirs(out_dir, exist_ok=True)
    file_count = 0

    # meta.json
    rated_players = sum(
        1 for r in records.values() if len(r["history"]) >= MIN_RATED_CONTESTS
    )
    meta = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "engine": ENGINE,
        "counts": {
            "contests": len(contest_docs),
            "players": len(records),
            "ratedPlayers": rated_players,
        },
    }
    _dump_json(os.path.join(out_dir, "meta.json"), meta)
    file_count += 1

    # contests-index.json + contests/<slug>.json
    index = []
    for doc in contest_docs:
        index.append(
            {
                "id": doc["id"],
                "slug": doc["slug"],
                "title": doc["title"],
                "startAt": doc["startAt"],
                "category": doc["category"],
                "teamCount": doc["teamCount"],
                "champion": doc["_champion"],
                "unrated": doc.get("unrated", False),
            }
        )
        detail = {k: v for k, v in doc.items() if k != "_champion"}
        _dump_json(
            os.path.join(out_dir, "contests", doc["slug"] + ".json"), detail
        )
        file_count += 1
    _dump_json(os.path.join(out_dir, "contests-index.json"), index)
    file_count += 1

    # players-index.json
    _dump_json(
        os.path.join(out_dir, "players-index.json"), build_players_index(records)
    )
    file_count += 1

    # period-index.json (official-participation timelines for the 时间段 board)
    _dump_json(
        os.path.join(out_dir, "period-index.json"), build_period_index(records)
    )
    file_count += 1

    # players/<shard>.json (256 buckets)
    shards: dict[str, dict] = {}
    for key, record in records.items():
        shards.setdefault(player_shard(key), {})[key] = record
    for shard, bucket in shards.items():
        _dump_json(os.path.join(out_dir, "players", shard + ".json"), bucket)
        file_count += 1

    # leaderboard.json (main board: all participation)
    _dump_json(
        os.path.join(out_dir, "leaderboard.json"),
        build_leaderboard(engine),
    )
    file_count += 1

    # leaderboard_official.json (second board: official participation only)
    if official_board is not None:
        _dump_json(
            os.path.join(out_dir, "leaderboard_official.json"),
            official_board,
        )
        file_count += 1

    return file_count


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="xcpc_rating.export_web",
        description="Export the static web data bundle for the xcpc-rating site.",
    )
    parser.add_argument("--data", default=DEFAULT_DATA, help="root of official srk collection")
    parser.add_argument("--out", default=DEFAULT_OUT, help="output directory for web JSON")
    parser.add_argument(
        "--min-coverage",
        type=float,
        default=0.0,
        help="optional extra member-list coverage floor; the default 0.0 admits "
             "any board with >= 1 rostered row (a no-roster board is always "
             "dropped)",
    )
    return parser


def run(args) -> int:
    started = time.perf_counter()
    print(f"Loading contests from {args.data} (min_coverage={args.min_coverage}) ...", flush=True)
    load = load_contests(args.data, min_coverage=args.min_coverage)
    print(
        f"Loaded {len(load.contests)} contests, "
        f"skipped {len(load.skipped)}, {len(load.warnings)} warnings.",
        flush=True,
    )

    contest_docs, players, engine = replay_and_collect(load.contests, args.data)

    # Tiered gold/silver/bronze medals, re-derived read-only from the raw srk
    # standings. Reuse the existing LoadResult so medals share the pipeline's
    # scan, dedup, and coverage decisions instead of re-loading from disk.
    medals = collect_medals(args.data, min_coverage=args.min_coverage, load_result=load)
    medalists = sum(1 for tally in medals.values() if _compact_medals(tally))
    print(f"Collected medals for {medalists} medalists.", flush=True)

    # Second board: replay again counting only official participation (打星 /
    # official:false teams treated as absent -- no field, no rank, no score). The
    # same replay collects each player's per-contest official perf/rating and the
    # per-contest official team docs, so the player and contest pages can render
    # the official-only 口径.
    official_history, official_contest_teams, engine_official = replay_official(
        load.contests
    )
    official_board = build_leaderboard(engine_official)
    print(f"Official-only board: {len(official_board)} rated players.", flush=True)

    # Merge the official-only per-team fields into each contest doc's teams, so the
    # contest page's 仅正式 view can render official ranks / predictions / perf. A
    # 打星 team has no official entry -> its *Official fields stay null.
    for doc in contest_docs:
        off_teams = official_contest_teams.get(doc["slug"], {})
        for i, team in enumerate(doc["teams"]):
            o = off_teams.get(i)
            team["predictedRankOfficial"] = o["predictedRank"] if o else None
            team["perfOfficial"] = o["perf"] if o else None
            team["preRatingOfficial"] = o["preRating"] if o else None
            team["muDeltaOfficial"] = o["muDelta"] if o else None
            team["rankOfficial"] = o["rank"] if o else None

    records = build_player_records(
        players, engine, medals=medals, official_history=official_history
    )
    file_count = write_bundle(
        args.out, contest_docs, records, engine, official_board=official_board
    )

    elapsed = time.perf_counter() - started
    print(
        f"Exported {file_count} files for {len(contest_docs)} contests / "
        f"{len(records)} players to {args.out} in {elapsed:.2f}s",
        flush=True,
    )
    return 0


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
