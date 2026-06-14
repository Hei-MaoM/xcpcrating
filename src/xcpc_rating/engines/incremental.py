"""Incremental ladder rating engine (the single scoring rule).

Everyone displays from 0 and carries an internal expected performance ``E``; the
score is built up contest by contest. Per contest the rating takes one bounded
step toward the performance the player achieved, so old results fade
geometrically (each update keeps ``1 - K`` of the past) rather than being
dropped, and a single number fully describes a player.

The rules (one line of the update each)
---------------------------------------
* **Internal expectation** ``E`` starts at ``INITIAL_EXPECT`` (1500). Everything
  field-related uses ``E``: LSE team strength, seeds / performance inversion
  (shared :mod:`xcpc_rating.perf`), predicted ranks, and ``predict_scores``.
* **Update**: ``E += K * tier_weight * (perf - E)`` -- a bounded step toward this
  contest's performance, scaled by the tier prestige weight.
* **CF-pure performance**: every rank's performance comes from the shared
  geometric-mean inversion (the Codeforces formula); the bounded K-step keeps a
  favourite's championship performance from running away.
* **达预期不扣分**: a team whose actual rank <= pre-contest predicted rank has its
  step floored at 0 -- meeting or beating expectation never deducts. Champions
  always qualify; under-performers take the full signed step.
* **Eligibility gates**: a provincial contest only counts for players whose
  pre-contest ``E`` is below the provincial gate, an invitational below the
  invitational gate; regionals and finals are unrestricted. A gated-out row
  changes nothing (no step, no rated-contest count) but stays visible with its
  performance. ``contests`` counts rated contests (drives the boost and the
  newcomer fade); ``played`` counts all participation (the public 场次).
* **Display from 0**: ``display = max(0, E - NEWCOMER_OFFSET * NEWCOMER_FADE^n)``
  where ``n`` is rated contests played, so a fresh player displays exactly 0 and
  the offset fades geometrically until a veteran displays ~``E``. Expectation and
  prediction always use ``E``, never the display value.

Geometric forgetting is built into the update, so nothing is ever deleted; an
optional idle-decay term regresses a long-idle ``E`` toward the prior.
"""

from __future__ import annotations

from .. import perf
from ..perf import GHOST_TEAM_SIZE
from ..tier import TIER_CAPS, TIER_FINAL, TIER_WEIGHTS, classify_tier
from .base import PlayerRating, RatingEngine

# Final-tier opponent-field floor. Used only on Final-tier performance solves,
# and only behind the off-by-default ``use_final_floor`` switch and the
# non-cf-pure champion-anchor branch, so a default Final never touches it.
FINAL_FIELD_FLOOR = 2800.0


def rerank_1224(teams) -> list:
    """1224-style competition ranks over the participated subset.

    ``teams`` is the scoring subset (participated rows only) in standings order.
    The loader assigned the full board its 1224 ranks over ``(solved, penalty)``;
    dropping non-participated rows can leave gaps, so this compacts the surviving
    teams back to a gapless 1224 sequence by walking standings order and bumping
    the rank only when the original ``team.rank`` changes -- tied teams stay tied
    and the certified relative order is preserved. Non-participated teams are
    0-solve rows at the bottom, so this only affects the rare mid-board absentee.
    """
    ranks = []
    prev_original = None
    current_rank = 0
    for idx, team in enumerate(teams):
        if idx == 0 or team.rank != prev_original:
            current_rank = idx + 1
        ranks.append(current_rank)
        prev_original = team.rank
    return ranks


def predicted_ranks(strengths) -> list:
    """Pre-contest predicted rank per team from pre-contest strengths (1224).

    ``strengths[i]`` is team ``i``'s pre-contest strength (the LSE aggregate the
    performance solve consumes). The predicted rank is the team's position when
    the field is sorted by strength descending, 1-based, with ties sharing the
    smallest (best) rank -- the same 1224 convention the standings use, so
    "actual_rank <= predicted_rank" compares like with like. Returned in the
    original team order, so it zips directly with the recovered performances.

    Example: strengths ``[1800, 2000, 2000, 1500]`` -> the two 2000s tie for rank
    1, 1800 is rank 3, 1500 is rank 4 -> ``[3, 1, 1, 4]``.
    """
    n = len(strengths)
    # Indices sorted by strength descending (strongest first).
    order = sorted(range(n), key=lambda i: strengths[i], reverse=True)
    ranks = [0] * n
    prev_strength = None
    current_rank = 0
    for position, idx in enumerate(order):
        s = strengths[idx]
        # New (worse) rank only when strength strictly drops; ties share the rank.
        if position == 0 or s != prev_strength:
            current_rank = position + 1
        ranks[idx] = current_rank
        prev_strength = s
    return ranks

# Initial expected performance: a fresh player's internal expectation, used for
# team strength / seeding / prediction from contest one.
INITIAL_EXPECT = 1500.0

# Base step size toward each contest's performance, scaled by the tier prestige
# weight.
K_BASE = 0.30

# Newcomer step boost (adaptive K): a player's n-th contest uses
#   k_eff = K_BASE * tier_weight * (1 + EARLY_BOOST * EARLY_FADE^n)
# capped at K_MAX. Early contests move the expectation fast so a few-contest elite
# converges quickly; veterans settle to the steady K. Boost of 0 disables.
EARLY_BOOST = 1.5
EARLY_FADE = 0.5
K_MAX = 0.85

# Time-gap step boost. The ladder forgets in contest-count space, so a player who
# returns after a long absence stays anchored by a stale ``E``. The longer since
# the last contest, the larger the next step, letting fresh evidence override the
# stale anchor faster. Symmetric (a weaker returnee also drops fast), additive to
# the newcomer boost, and capped at K_MAX:
#   k_eff = K_BASE * tier_weight * (1 + EARLY_BOOST*EARLY_FADE^n + gap_boost)
#   gap_boost = GAP_BOOST_MAX * (1 - 0.5^(beyond_grace_days / GAP_HALFLIFE_DAYS))
# A gap within GAP_GRACE_DAYS adds nothing, so normal multi-event seasons are
# untouched; only a genuine long absence inflates the step. GAP_BOOST_MAX = 0
# disables. Values are tunable via the constructor.
GAP_BOOST_MAX = 1.0
GAP_GRACE_DAYS = 200.0
GAP_HALFLIFE_DAYS = 180.0

# Champion-solve opponent pool size (used only on the non-cf-pure branch).
CHAMP_TOPK = 10

# Newcomer display offset: display = max(0, E - OFFSET * FADE^n). OFFSET equals
# INITIAL_EXPECT so contest count 0 displays exactly 0; FADE sets how many
# contests it takes to surface a player's real level (a debut leaves 600, ~38
# after the 4th contest).
NEWCOMER_OFFSET = 1500.0
NEWCOMER_FADE = 0.4

# Idle decay: E regresses toward INITIAL_EXPECT by this factor per 30 idle days
# beyond the grace period, so a long-retired player fades off the board head
# instead of freezing there. A normal season gap (within the grace period) costs
# nothing. 1.0 = off.
IDLE_DECAY_PER_30D = 1.0
IDLE_GRACE_DAYS = 240.0
SECONDS_PER_30D = 30 * 24 * 3600.0
SECONDS_PER_DAY = 24 * 3600.0

# Ghost teams (no roster) stand in for three fresh expectations (~1690.85).
GHOST_EXPECT = perf.lse_aggregate([INITIAL_EXPECT] * GHOST_TEAM_SIZE)

# The amount by which a full three-person team's LSE aggregate sits above a single
# member (~400*log10(3) ~= 190.85). Performance is inverted on the team scale but
# the step is consumed on the individual scale; subtracting this offset re-bases
# the step onto the individual scale, so an all-fresh field does not mint score
# before any rank is earned.
TEAM_SCALE_OFFSET = perf.lse_aggregate([INITIAL_EXPECT] * GHOST_TEAM_SIZE) - INITIAL_EXPECT

# Eligibility gates: a tier-t contest only counts for a player whose pre-contest
# expectation is below GATE[t]. A gated-out contest changes nothing (no E step, no
# rated-contest count; the row stays as display-only participation with its
# performance shown); the field model still includes everyone. Regionals and
# finals are unrestricted (None).
TIER_GATES = {
    "final": None,
    "regional": None,
    "invitational": 2150.0,
    "provincial": 1950.0,
}

# Tiered field floor: before reverse-solving performance, lift every team's
# pre-contest LSE strength to ``max(S, floor_t)`` for tier t (None = no floor).
# Only the weak tail is raised; teams above the floor keep their own strength.
# Treating a regional as a structurally stronger pool than an invitational lets
# the same rank reverse-solve a higher performance, so the tiers pull apart in
# discrimination. This is not FINAL_FIELD_FLOOR, which raised every team uniformly.
TIER_FIELD_FLOOR = {
    "final": None,
    "regional": 1900.0,
    "invitational": 1600.0,
    "provincial": None,
}


def predicted_ranks_midpoint(strengths) -> list:
    """Predicted ranks from pre-contest strengths, tied blocks at the *midpoint*.

    Same descending sort as :func:`predicted_ranks`, but a block of tied teams
    shares the **midpoint** of the rank interval it spans rather than the best
    (smallest) shared rank. A block occupying 1-based positions ``a..b`` is
    assigned ``(a + b) / 2`` for every member (possibly fractional).

    The 1224 convention gives every team in a tied block the block's best rank, so
    when a whole field shares one strength (an all-fresh field) every team predicts
    rank 1 and only the champion is judged to have met expectation. The midpoint
    places the tied block at the centre of its interval, so roughly half lands
    at-or-above expectation and half below -- a symmetric verdict for an
    a-priori-symmetric field.

    Example: strengths ``[1800, 2000, 2000, 1500]`` -> the two 2000s occupy
    positions 1..2 (midpoint 1.5), 1800 is position 3, 1500 is position 4 ->
    ``[3.0, 1.5, 1.5, 4.0]``.
    """
    n = len(strengths)
    # Indices sorted by strength descending (strongest first) -- same as the
    # 1224 predicted_ranks, only the per-block rank value differs.
    order = sorted(range(n), key=lambda i: strengths[i], reverse=True)
    ranks = [0.0] * n
    block_start = 0
    while block_start < n:
        # Extend the block over every equal-strength neighbour.
        block_end = block_start
        s = strengths[order[block_start]]
        while block_end + 1 < n and strengths[order[block_end + 1]] == s:
            block_end += 1
        # 1-based interval [block_start+1 .. block_end+1]; share its midpoint.
        midpoint = ((block_start + 1) + (block_end + 1)) / 2.0
        for position in range(block_start, block_end + 1):
            ranks[order[position]] = midpoint
        block_start = block_end + 1
    return ranks


def newcomer_offset(contests: int) -> float:
    """The display deduction after ``contests`` rated contests (fades to ~0)."""
    return NEWCOMER_OFFSET * (NEWCOMER_FADE ** contests)


def display_score(expect: float, contests: int) -> float:
    """User-facing score: expectation minus the fading newcomer offset, >= 0."""
    return max(0.0, expect - newcomer_offset(contests))


class IncrementalEngine(RatingEngine):
    """Chronological incremental ladder over shared performances."""

    name = "incremental"

    def __init__(self, k_base: float = K_BASE,
                 early_boost: float = EARLY_BOOST,
                 early_fade: float = EARLY_FADE,
                 idle_decay: float = IDLE_DECAY_PER_30D,
                 cf_pure_perf: bool = True,
                 use_gates: bool = True,
                 use_final_floor: bool = False,
                 final_avg_injection: float | None = 10.0,
                 team_relative_step: bool = False,
                 # When True the recorded/displayed performance is also shifted
                 # onto the individual scale; by default it stays team-scale and
                 # only the step is rebased (via individual_gain below).
                 member_scale_perf: bool = False,
                 baseline_floor: bool = False,
                 # When True the step (加减分) is computed on the individual scale:
                 # it subtracts the team LSE offset so a member is judged by whether
                 # the team's performance clears THEIR OWN level, not the team's
                 # rank. The displayed performance stays team-scale. This removes
                 # the team-scale minting artifact, so no_gain_below_expectation is
                 # unnecessary. Production default.
                 individual_gain: bool = True,
                 # When True a below-expectation team cannot gain (any positive step
                 # on an unmet row is zeroed) -- the symmetric counterpart to
                 # 达预期不扣分. Off by default (made unnecessary by individual_gain).
                 no_gain_below_expectation: bool = False,
                 # When True a below-expectation gain is kept if the performance
                 # clearly beats the player's own E (an exemption used with
                 # no_gain_below_expectation). Off by default.
                 overperf_keeps_gain: bool = False,
                 deduct_below_expectation: bool = False,
                 tier_field_floor: dict | None = None,
                 gate_removes_from_field: bool = True,
                 tier_gates: dict | None = None,
                 gap_boost_max: float = GAP_BOOST_MAX,
                 gap_grace_days: float = GAP_GRACE_DAYS,
                 gap_halflife_days: float = GAP_HALFLIFE_DAYS,
                 # Official-only board: when True a 打星 / official:false team is
                 # treated as absent -- no field slot, no rank, no score, no effect
                 # on other teams' performances.
                 official_only: bool = False) -> None:
        self.k_base = k_base
        self.early_boost = early_boost
        self.early_fade = early_fade
        self.idle_decay = idle_decay
        # Production defaults: CF-pure performance (every rank from the shared
        # geometric-mean inversion, no champion-solve override) and eligibility
        # gates instead of tier caps. cf_pure_perf=False restores the champion
        # anchor; use_gates=False restores the tier-cap path.
        self.cf_pure_perf = cf_pure_perf
        self.use_gates = use_gates
        # No Final field floor by default; the mean per-member step on final-tier
        # contests is forced to ``final_avg_injection`` (default 10).
        self.use_final_floor = use_final_floor
        self.final_avg_injection = final_avg_injection
        # When True the step baseline is the team's pre-contest LSE strength
        # S_team instead of each member's individual E: step = k_eff * (perf -
        # S_team), the whole team sharing one residual.
        self.team_relative_step = team_relative_step
        # When True the performance value is shifted onto the individual scale
        # before the step (perf_value -= TEAM_SCALE_OFFSET), so the step is
        # measured against a comparable quantity and recorded on the individual
        # scale. A uniform shift leaves seeds and predicted ranks (hence the
        # backtest concordance) unchanged.
        self.member_scale_perf = member_scale_perf
        # When True the step baseline is floored at the all-fresh three-person team
        # strength: step = k_eff * (perf - max(E, INITIAL_EXPECT +
        # TEAM_SCALE_OFFSET)). A player already above that floor keeps their
        # individual E unchanged. Mutually exclusive with member_scale_perf /
        # team_relative_step.
        self.baseline_floor = baseline_floor
        # When True, two changes keyed off predicted_ranks_midpoint: (a) the 达预期
        # verdict uses the midpoint rank, so an a-priori-symmetric field splits
        # ~half met / ~half not; (b) a below-expectation row gets any positive step
        # zeroed (未达预期不涨分).
        self.no_gain_below_expectation = no_gain_below_expectation
        # 加减分按个人算: the step subtracts TEAM_SCALE_OFFSET (individual scale)
        # while the recorded/displayed performance stays team-scale.
        self.individual_gain = individual_gain
        # 个人超常发挥兜底: keep a below-expectation gain when the performance
        # clearly beats the player's own E. Off by default.
        self.overperf_keeps_gain = overperf_keeps_gain
        # When True (mutually exclusive with no_gain_below_expectation, also keyed
        # off predicted_ranks_midpoint): a met row steps from the individual E
        # (step = k_eff * (perf - E), floored at 0); an unmet row steps from the
        # team's pre-contest LSE strength S_team (step = k_eff * (perf - S_team)),
        # which is necessarily a deduction under the midpoint predictions, with a
        # defensive min(step, 0) at the boundary.
        self.deduct_below_expectation = deduct_below_expectation
        # Tiered field floor (see TIER_FIELD_FLOOR): lift every team's pre-contest
        # strength to ``max(S, floor_t)`` before solving performance. None here
        # means use the module-level default; a caller may pass its own dict.
        self.tier_field_floor = (
            tier_field_floor if tier_field_floor is not None
            else TIER_FIELD_FLOOR
        )
        # When gates are on and this is True, a team fully above the tier gate
        # (every member's pre-contest E >= gate) is removed from the scoring field
        # entirely -- it does not seed, take a rank, or enter the performance
        # inversion. Its members still count as played (公共场次 advances, idle
        # clock refreshes) but record no performance and never score. False keeps
        # the legacy display-only gating.
        self.gate_removes_from_field = gate_removes_from_field
        # Eligibility gate thresholds. None => use the module-level TIER_GATES; a
        # caller may pass its own dict.
        self.tier_gates = (
            tier_gates if tier_gates is not None else TIER_GATES
        )
        # Time-gap step boost parameters (see GAP_* constants). gap_boost_max=0
        # disables the mechanism.
        self.gap_boost_max = gap_boost_max
        self.gap_grace_days = gap_grace_days
        self.gap_halflife_days = gap_halflife_days
        # Official-only board: 打星 / official:false teams are treated as absent.
        self.official_only = official_only
        # key -> {"expect", "contests", "played", "last_at", "last_perf",
        #         "display_name", "org"}
        self._players: dict[str, dict] = {}
        # Latest contest date seen; the leaderboard decays idle players to it.
        self._now = None

    # -- helpers -----------------------------------------------------------

    def _decayed_expect(self, state, now) -> float:
        """Expectation with idle decay applied up to ``now`` (lazy, read-only)."""
        expect = state["expect"]
        if self.idle_decay >= 1.0 or now is None or state["last_at"] is None:
            return expect
        idle_days = (now - state["last_at"]).total_seconds() / SECONDS_PER_DAY
        beyond_grace = idle_days - IDLE_GRACE_DAYS
        if beyond_grace <= 0:
            return expect
        factor = self.idle_decay ** (beyond_grace / 30.0)
        return INITIAL_EXPECT + (expect - INITIAL_EXPECT) * factor

    def _gap_boost(self, state, now) -> float:
        """Additive k-multiplier boost from the time since the last contest.

        Returns 0.0 for a brand-new player (no ``last_at``) or a short gap (<=
        ``gap_grace_days``); past the grace it ramps with a half-life of
        ``gap_halflife_days`` toward ``gap_boost_max``. A long-stale E is
        untrustworthy, so a returning player's next result moves them more.
        Read-only; the caller computes this before ``last_at`` is advanced to
        ``now``.
        """
        if self.gap_boost_max <= 0.0 or now is None or state["last_at"] is None:
            return 0.0
        gap_days = (now - state["last_at"]).total_seconds() / SECONDS_PER_DAY
        beyond = gap_days - self.gap_grace_days
        if beyond <= 0.0:
            return 0.0
        return self.gap_boost_max * (1.0 - 0.5 ** (beyond / self.gap_halflife_days))

    def _expect(self, member, now=None) -> float:
        state = self._players.get(member.key)
        if state is None:
            return INITIAL_EXPECT
        return self._decayed_expect(state, now)

    def _team_strength(self, members, now=None) -> float:
        if not members:
            return GHOST_EXPECT
        return perf.lse_aggregate([self._expect(m, now) for m in members])

    def _record_removed_teams(self, removed, now) -> None:
        """Record members of teams removed from the scoring field.

        A removed team's members count as having played (公共场次 advances and the
        idle clock refreshes) but earn no performance, no E step, and no rated
        contest. ``last_perf`` is cleared to ``None``.
        """
        for team in removed:
            for member in team.members:
                state = self._players.get(member.key)
                if state is None:
                    state = {
                        "expect": INITIAL_EXPECT,
                        "contests": 0,
                        "played": 0,
                        "last_at": None,
                        "last_perf": None,
                        "display_name": member.display_name,
                        "org": member.org,
                    }
                    self._players[member.key] = state
                state["played"] += 1
                state["display_name"] = member.display_name
                state["org"] = member.org
                state["last_perf"] = None
                state["last_at"] = now

    # -- RatingEngine API ----------------------------------------------------

    def _counts(self, team) -> bool:
        """Whether a team enters scoring: participated, and -- on the official-only
        board (``official_only``) -- officially ranked (打星/official:false excluded).
        """
        if not getattr(team, "participated", True):
            return False
        if self.official_only and not getattr(team, "official", True):
            return False
        return True

    def predict_scores(self, contest) -> list:
        now = contest.start_at
        return [
            self._team_strength(team.members, now)
            if self._counts(team)
            else GHOST_EXPECT
            for team in contest.teams
        ]

    def process_contest(self, contest) -> None:
        teams = [
            team for team in contest.teams
            if self._counts(team)
        ]
        if not teams:
            return
        now = contest.start_at
        if self._now is None or now > self._now:
            self._now = now
        tier = classify_tier(contest)
        k_tier = self.k_base * TIER_WEIGHTS[tier]
        cap = TIER_CAPS[tier]
        is_final = tier == TIER_FINAL

        # Gate-removes-from-field: when gates are on and the switch is set, a team
        # fully above the tier gate (every member's pre-contest E >= gate) is
        # removed from the scoring field entirely -- it does not seed, take a rank,
        # or enter the performance inversion. Such a team still counts as played
        # but records no performance and never scores. Ghost / roster-less teams
        # are always kept (they seed the pool).
        if self.use_gates and self.gate_removes_from_field:
            gate = self.tier_gates[tier]
            in_field = []
            removed = []
            for team in teams:
                if gate is None or not team.members or any(
                    self._expect(m, now) < gate for m in team.members
                ):
                    in_field.append(team)
                else:
                    removed.append(team)
            self._record_removed_teams(removed, now)
            teams = in_field
            if not teams:
                return

        strengths = [
            self._team_strength(team.members, now) for team in teams
        ]
        field = list(strengths)
        floor_t = self.tier_field_floor.get(tier)
        if floor_t is not None:
            # Lift the weak tail of the field to the tier floor before solving
            # performance. Teams already above floor_t keep their strength.
            field = [max(s, floor_t) for s in field]
        if is_final and self.use_final_floor:
            # The Final-only field floor is an independent branch (off by default,
            # and TIER_FIELD_FLOOR["final"] is None, so a default Final touches
            # neither floor).
            field = [max(s, FINAL_FIELD_FLOOR) for s in field]
        ranks = rerank_1224(teams)
        performances = perf.compute_performances(field, ranks)

        # Champion solve: self-excluded, strongest-member anchored, top-K. The
        # cf-pure path skips this override (every rank uses the shared
        # geometric-mean inversion, exactly the Codeforces formula).
        if not self.cf_pure_perf:
            anchors = []
            for team in teams:
                anchor = max(
                    (self._expect(m, now) for m in team.members),
                    default=INITIAL_EXPECT,
                )
                anchors.append(max(anchor, FINAL_FIELD_FLOOR) if is_final
                               else anchor)
            for i, rank_i in enumerate(ranks):
                if rank_i == 1:
                    performances[i] = perf.champion_performance(
                        anchors, i, top_k=CHAMP_TOPK
                    )

        # 达预期 verdict input: the 1224 best-rank predictions by default, or the
        # tied-block-midpoint predictions when no_gain_below_expectation or
        # deduct_below_expectation is on (so an a-priori-symmetric field splits
        # ~half met / ~half not, instead of only the champion meeting expectation).
        predictions = (
            predicted_ranks_midpoint(strengths)
            if (self.no_gain_below_expectation or self.deduct_below_expectation)
            else predicted_ranks(strengths)
        )

        # Steps are buffered so a final-tier contest can apply the average-change
        # injection uniformly before committing.
        pending: list[tuple[dict, float, float]] = []
        for team, perf_i, rank_i, predicted, strength_i in zip(
                teams, performances, ranks, predictions, strengths):
            perf_value = float(perf_i)
            if self.member_scale_perf:
                # Re-base the team-scale performance onto the individual scale so
                # the step is measured against a comparable quantity. Uniform
                # shift => seeds / predicted ranks unchanged; recorded as last_perf
                # too (individual-scale export).
                perf_value -= TEAM_SCALE_OFFSET
            met = rank_i <= predicted
            for member in team.members:
                state = self._players.get(member.key)
                if state is None:
                    state = {
                        "expect": INITIAL_EXPECT,
                        "contests": 0,   # rated contests (drive boost + fade)
                        "played": 0,     # all participated (public 场次)
                        "last_at": None,
                        "last_perf": None,
                        "display_name": member.display_name,
                        "org": member.org,
                    }
                    self._players[member.key] = state
                state["played"] += 1
                state["display_name"] = member.display_name
                state["org"] = member.org
                # This contest's recovered performance is recorded even for a
                # gated-out row (the contest page still shows what level the team
                # played at).
                state["last_perf"] = perf_value
                # Idle decay materializes on touch: the update steps from the
                # decayed level, and last_at advances to this contest.
                expect = self._decayed_expect(state, now)
                if self.use_gates:
                    # Eligibility gate: this tier only counts below its gate;
                    # otherwise nothing happens (no step, no rated count -- the row
                    # is display-only participation).
                    gate = self.tier_gates[tier]
                    if gate is not None and expect >= gate:
                        # Gated-out still counts as active: participation refreshes
                        # the idle clock, so a high-frequency player grinding
                        # low-tier contests is not wrongly decayed if idle_decay is
                        # ever enabled.
                        state["last_at"] = now
                        continue
                # Newcomer boost (by rated-contest count) plus the time-gap boost
                # (by days since this member's last contest): both enlarge the step
                # so a stale or early anchor is overridden faster. ``last_at`` still
                # holds the previous contest's date here (it advances to ``now``
                # only after the step below).
                boost = (
                    1.0
                    + self.early_boost * (self.early_fade ** state["contests"])
                    + self._gap_boost(state, now)
                )
                k_eff = min(k_tier * boost, K_MAX)
                if self.team_relative_step:
                    # Team-residual baseline: the whole team shares one residual
                    # measured against its pre-contest LSE strength (perf is on the
                    # team scale), instead of each member's individual E.
                    step = k_eff * (perf_value - strength_i)
                elif self.baseline_floor:
                    # Baseline floor: judge a sub-team-baseline player against the
                    # all-fresh three-person team strength (E + offset) rather than
                    # their lower individual E. Players already at or above the
                    # baseline keep their individual E (max picks E).
                    baseline = max(expect, INITIAL_EXPECT + TEAM_SCALE_OFFSET)
                    step = k_eff * (perf_value - baseline)
                elif self.deduct_below_expectation:
                    # Met rows keep the individual baseline E; unmet rows switch to
                    # the team's pre-contest LSE strength S_team (strength_i). Under
                    # the midpoint predictions an unmet rank reverse-solves
                    # perf < S_team, so the unmet step is always a deduction.
                    if met:
                        step = k_eff * (perf_value - expect)
                    else:
                        step = k_eff * (perf_value - strength_i)
                        # Defensive: clamp any tie-edge / floating-point residual to
                        # a non-gain so an unmet row can never pay out.
                        step = min(step, 0.0)
                else:
                    # 加减分按个人算: the step measures the team performance against
                    # the member's OWN level by subtracting the team LSE offset.
                    # perf_value (the displayed performance) stays team-scale; only
                    # this step quantity is rebased. Don't subtract twice when
                    # member_scale_perf already rebased perf_value.
                    gain_perf = perf_value
                    if self.individual_gain and not self.member_scale_perf:
                        gain_perf = perf_value - TEAM_SCALE_OFFSET
                    step = k_eff * (gain_perf - expect)
                if met and step < 0.0:
                    # 达预期不扣分: meeting or beating expectation never deducts.
                    step = 0.0
                if self.no_gain_below_expectation and not met and step > 0.0:
                    # 未达预期不涨分: a below-expectation team cannot gain. perf is
                    # solved on the team scale, so on an all-fresh field even a
                    # bottom team's perf sits above the individual prior and would
                    # otherwise pay a positive K-step it did not earn; this clips
                    # exactly those rows. The optional 个人超常发挥兜底
                    # (overperf_keeps_gain) keeps the gain when the recovered
                    # performance clearly exceeds the player's own E by more than
                    # the team-scale offset (real individual over-performance, not
                    # the fresh-team minting artifact).
                    overperf_margin = (
                        0.0 if self.member_scale_perf else TEAM_SCALE_OFFSET
                    )
                    overperformed = (
                        self.overperf_keeps_gain
                        and perf_value > expect + overperf_margin
                    )
                    if not overperformed:
                        step = 0.0
                if step > 0.0 and not self.use_gates:
                    # Tier cap: an upward step cannot cross cap_t; at/above the cap
                    # this tier's contests stop paying. (The gate variant replaces
                    # caps entirely: no ceiling on counted contests.)
                    ceiling = max(expect, cap)
                    step = min(expect + step, ceiling) - expect
                pending.append((state, expect, step))

        # Final-tier average-change injection: shift every counted member's step
        # uniformly so the mean step equals ``final_avg_injection``. Applied after
        # the met-expectation floor, so a met team can move slightly negative on a
        # Final when the field ran hot while the pool's growth stays at n*x.
        inc = 0.0
        if (is_final and self.final_avg_injection is not None and pending):
            mean_step = sum(s for _st, _e, s in pending) / len(pending)
            inc = self.final_avg_injection - mean_step
        for state, expect, step in pending:
            state["expect"] = expect + step + inc
            state["contests"] += 1
            state["last_at"] = now

    def leaderboard(self, min_contests: int = 1) -> list:
        entries = []
        for key, state in self._players.items():
            # The public 场次 is every participated contest (gated display-only
            # rows included), matching the player page's history length; the
            # newcomer fade still runs on rated contests only.
            played = state.get("played", state["contests"])
            if played < min_contests:
                continue
            # Board semantics: current state as of the corpus's latest contest --
            # idle players decay toward the initial expectation.
            expect = self._decayed_expect(state, self._now)
            entries.append(
                PlayerRating(
                    key=key,
                    display_name=state["display_name"],
                    org=state["org"],
                    rating=display_score(expect, state["contests"]),
                    contests=played,
                    extra={"expect": expect},
                )
            )
        entries.sort(key=lambda p: p.rating, reverse=True)
        return entries
