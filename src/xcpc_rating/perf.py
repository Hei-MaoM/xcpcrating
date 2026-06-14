"""Shared performance-rating mechanism.

These pure, numpy-vectorized functions recover each team's performance rating
``R*`` from a field of pre-contest team strengths and the realized standings --
one definition of "what level a team played at this contest":

1. **LSE team aggregation** (:func:`lse_aggregate`): a team behaves like its
   strongest member in Elo win-odds space.
2. **Seeds** (:func:`compute_seeds`): the classic Elo pairwise expected rank.
3. **Performance ratings** (:func:`compute_performances`): solve
   ``g(R) = sqrt(seed * actual_rank)`` per team via vectorized batch bisection.

No state is held here; callers persist samples however they wish.
"""

import math

import numpy as np

INITIAL_RATING = 1500.0
ELO_SCALE = 400.0
PERF_LOW = -2000.0
PERF_HIGH = 6000.0
BISECTION_ITERS = 60
# A ghost team (no members) stands in for a prior-strength squad of three
# rookies; its LSE strength is fixed and never persisted.
GHOST_TEAM_SIZE = 3
# Champion-performance loss budget: the rating R at which beating the *entire*
# field is a coin flip satisfies prod_j (1 - P_loss_j) = 1/2, i.e. exactly
# sum_j -ln(1 - P_loss_j) = ln 2. (The small-p first-order form sum_j P_loss_j
# = ln 2 over-spends the budget when one opponent dominates: with a single
# equal opponent it would place the champion *below* them, where the exact form
# correctly returns "level with the best opponent".) See champion_performance.
CHAMPION_LOSS_BUDGET = math.log(2.0)


def lse_aggregate(member_strengths) -> float:
    """LSE aggregation of member strengths in Elo win-odds space.

    ``r_team = 400 * log10( sum_k 10 ** (s_k / 400) )``, evaluated stably by
    factoring out the maximum first. Guaranteed bounds:

        max(s_k) <= r_team <= max(s_k) + 400 * log10(len(s_k))

    An empty input is treated as a ghost team of ``GHOST_TEAM_SIZE`` priors, so
    a roster-less team reports the fixed prior aggregate (~1690.85).
    """
    if len(member_strengths) == 0:
        member_strengths = [INITIAL_RATING] * GHOST_TEAM_SIZE
    arr = np.asarray(member_strengths, dtype=float)
    peak = float(arr.max())
    # Subtract the peak so the largest exponent is 10**0 == 1 (stable sum).
    odds_sum = float(np.sum(np.power(10.0, (arr - peak) / ELO_SCALE)))
    return ELO_SCALE * math.log10(odds_sum) + peak


def _win_prob_matrix(ratings: np.ndarray) -> np.ndarray:
    """Pairwise P(i beats j) under the Elo logistic curve, as an NxN matrix.

    Entry ``[i, j]`` is ``1 / (1 + 10**((r_j - r_i) / 400))``. The diagonal is
    0.5 and is excluded by callers when summing over ``j != i``.
    """
    diff = ratings[None, :] - ratings[:, None]  # diff[i, j] = r_j - r_i
    return 1.0 / (1.0 + np.power(10.0, diff / ELO_SCALE))


def compute_seeds(team_ratings) -> np.ndarray:
    """Expected rank for each team: ``seed_i = 1 + sum_{j!=i} P(j beats i)``.

    ``P(j beats i) = 1 - P(i beats j)``; summing the loss column and removing
    the self term (0.5) gives the seed. Two equally-rated teams each seed 1.5.
    """
    ratings = np.asarray(team_ratings, dtype=float)
    win = _win_prob_matrix(ratings)  # win[i, j] = P(i beats j)
    loss = 1.0 - win  # loss[i, j] = P(j beats i)
    # sum over j of loss[i, j] includes the diagonal (0.5); subtract it.
    return 1.0 + (loss.sum(axis=1) - 0.5)


def _expected_ranks_at(perf: np.ndarray, ratings: np.ndarray) -> np.ndarray:
    """Vectorized ``g(R_i) = 1 + sum_{j!=i} 1/(1+10**((R_i - r_j)/400))``.

    ``perf`` holds one candidate performance rating per team; ``ratings`` holds
    the fixed pre-contest team ratings of the whole field. The double broadcast
    builds an NxN matrix of probabilities that team ``i`` (at ``perf[i]``) loses
    to opponent ``j`` (at ``ratings[j]``). The ``j == i`` term contributes
    exactly 0.5 and is subtracted off rather than masked.
    """
    diff = perf[:, None] - ratings[None, :]  # diff[i, j] = perf_i - r_j
    prob = 1.0 / (1.0 + np.power(10.0, diff / ELO_SCALE))
    return 1.0 + (prob.sum(axis=1) - 0.5)


def _solve_performances(targets: np.ndarray, ratings: np.ndarray) -> np.ndarray:
    """Solve ``g(R_i) = targets_i`` for every team via batch bisection.

    ``g`` is strictly decreasing in ``R``, so a standard bisection on the fixed
    bracket ``[PERF_LOW, PERF_HIGH]`` converges for all teams simultaneously.
    """
    n = len(ratings)
    low = np.full(n, PERF_LOW, dtype=float)
    high = np.full(n, PERF_HIGH, dtype=float)
    for _ in range(BISECTION_ITERS):
        mid = 0.5 * (low + high)
        g_mid = _expected_ranks_at(mid, ratings)
        # g decreasing: if g(mid) > target, R is too small -> raise the floor.
        too_strong = g_mid > targets
        low = np.where(too_strong, mid, low)
        high = np.where(too_strong, high, mid)
    return 0.5 * (low + high)


def champion_performance(team_ratings, champion_index: int,
                         top_k: int | None = None) -> float:
    """Right-censored champion performance: "beating this whole field = 50%".

    The geometric-mean target of :func:`compute_performances` leaks a team's
    *own* pre-contest rating into its own performance via the seed: a strong
    favourite has ``seed ~= 1``, so winning forces the solved ``R*`` up to a
    level that beats every opponent with near-certainty (field-top + 1500..1900)
    -- a rich-get-richer feedback that inflates the whole top of the scale. But a
    win is a *right-censored* observation: it only proves a lower bound, and the
    statistically honest location for that bound is the level at which winning
    the contest outright was a coin flip.

    So for a rank-1 team this solves, over the *opponents only* (its own rating
    is excluded entirely -- no self-leak),

        prod_{j != i} (1 - P(R loses to r_j)) = 1/2
        <=>  sum_{j != i} -ln(1 - P(R loses to r_j)) = ln 2

    The left side of the log form is strictly decreasing in ``R``, so bisection
    on the same ``[PERF_LOW, PERF_HIGH]`` bracket converges. Properties: with a
    single equal opponent the solution is exactly that opponent's rating
    (beating one equal team once proves parity, no more); when one rival
    dominates the field it sits at/just above that rival ("about as good as the
    best of them"); over a flat field it grows with field size roughly as
    ``r + 400*log10(N / ln 2)``. Consumed for rank-1 teams only on the
    non-cf-pure path; the default cf-pure solve leaves every rank untouched.

    ``top_k`` (optional) restricts the opponent pool to the K strongest
    opponents: "winning this contest" is then read as "beating its title
    contenders", so the certified bound tracks the head of the field rather
    than growing another ``+400*log10(N)`` margin from sweeping a long tail of
    weak teams (the field-size inflation the tier system exists to fight).

    A field with no opponents (single-team contest) degenerately returns the
    team's own rating.
    """
    ratings = np.asarray(team_ratings, dtype=float)
    opponents = np.delete(ratings, champion_index)
    if opponents.size == 0:
        return float(ratings[champion_index])
    if top_k is not None and opponents.size > top_k:
        opponents = np.sort(opponents)[-top_k:]
    low, high = PERF_LOW, PERF_HIGH
    for _ in range(BISECTION_ITERS):
        mid = 0.5 * (low + high)
        loss = 1.0 / (1.0 + np.power(10.0, (mid - opponents) / ELO_SCALE))
        spent = float(-np.log1p(-loss).sum())  # sum_j -ln(1 - p_j), exact form
        # Budget decreasing in R: above ln 2 means R is still too weak.
        if spent > CHAMPION_LOSS_BUDGET:
            low = mid
        else:
            high = mid
    return 0.5 * (low + high)


def compute_performances(team_ratings, ranks) -> np.ndarray:
    """Recover each team's performance rating ``R*`` from the standings.

    Given the pre-contest team strengths ``team_ratings`` and the realized
    ``ranks``, compute each team's seed, form the per-team geometric-mean target
    ``m_i = sqrt(seed_i * rank_i)``, and invert ``g(R_i) = m_i`` for the
    performance rating ``R*_i``. ``R*_i`` is the level team ``i`` actually played
    at this contest -- one performance sample for each of its members.
    """
    ratings = np.asarray(team_ratings, dtype=float)
    actual_ranks = np.asarray(ranks, dtype=float)
    seeds = compute_seeds(ratings)
    targets = np.sqrt(seeds * actual_ranks)  # geometric mean m_i
    return _solve_performances(targets, ratings)
