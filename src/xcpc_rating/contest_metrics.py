"""Pre-contest field strength and post-contest result weirdness.

The strength metrics use every official, participated team. Every team occupies
one full strength slot; there is no completeness weighting. A wholly unknown
roster is still represented by the prediction engine's pre-contest default
strength.

Result ranks enter only the weirdness metric. Weirdness compares the relative
ordering of complete-history teams (all three members known) so an uncertain
partial roster can neither create a surprise itself nor displace otherwise
predictable teams.

Six independent strength scores are emitted:

* bronze / silver / gold medal-cut difficulty;
* top-3 / top-10 difficulty;
* overall field difficulty.

There is deliberately no composite strength score and no 0–100 mapping. Every
strength value stays on the pre-contest team-rating scale and is only intended
for comparison among contests from the same year.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable


ELO_SCALE = 400.0

# Weirdness gives top-rank displacement priority while retaining a smaller
# linear all-field component.  Elo confidence can modulate a rank displacement
# by at most 20%, so it distinguishes a 400-point upset from a near toss-up
# without overturning the rank-position policy.
WEIRDNESS_TOP_SHARE = 0.75
WEIRDNESS_LINEAR_SHARE = 1.0 - WEIRDNESS_TOP_SHARE
WEIRDNESS_CONFIDENCE_SHARE = 0.20
COMPLETE_HISTORY_MEMBER_COUNT = 3

_STRENGTH_KEYS = (
    "bronze",
    "silver",
    "gold",
    "top3",
    "top10",
    "overall",
)


@dataclass(frozen=True)
class MetricTeam:
    """One team as seen by the contest-metric layer.

    ``rating`` is its pre-contest official-only team rating. ``actual_rank`` is
    its realized rank; ties may share a value. ``known_members`` is the number
    of roster members with at least one rated official contest before this
    event. Strength admits every official participating team regardless of
    history completeness. Weirdness requires the normal three-member roster to
    be fully known.
    """

    rating: float
    actual_rank: float
    known_members: int
    official: bool = True
    participated: bool = True


def _strength_candidates(teams: Iterable[MetricTeam]) -> list[MetricTeam]:
    """Official participating teams with finite pre-match/result values."""
    candidates = []
    for team in teams:
        if not team.official or not team.participated:
            continue
        if not math.isfinite(team.rating) or not math.isfinite(team.actual_rank):
            continue
        candidates.append(team)
    return candidates


def medal_cutoffs(effective_team_count: int) -> dict[str, int]:
    """Cumulative medal boundaries requested by the user.

    Gold is ``ceil(10% * N)``; silver is twice that gold boundary and bronze is
    three times it, each clamped to the effective field.
    """
    n = max(0, int(effective_team_count))
    if n == 0:
        return {"gold": 0, "silver": 0, "bronze": 0}
    gold = max(1, math.ceil(n * 0.10))
    return {
        "gold": gold,
        "silver": min(n, gold * 2),
        "bronze": min(n, gold * 3),
    }


def _elo_probability(first_rating: float, second_rating: float) -> float:
    """Probability that ``first_rating`` ranks ahead of ``second_rating``."""
    exponent = (second_rating - first_rating) / ELO_SCALE
    # Avoid overflow for malformed/extreme input while preserving the limit.
    if exponent >= 16.0:
        return 0.0
    if exponent <= -16.0:
        return 1.0
    return 1.0 / (1.0 + 10.0**exponent)


def _cutoff_rating(teams: list[MetricTeam], cutoff: int) -> float:
    """Rating whose expected rank is halfway across the requested boundary."""
    n = len(teams)
    if not 1 <= cutoff <= n:
        raise ValueError("cutoff must lie inside the effective field")

    ratings = [team.rating for team in teams]
    target_rank = cutoff + 0.5

    low = min(ratings) - 8.0 * ELO_SCALE
    high = max(ratings) + 8.0 * ELO_SCALE
    for _ in range(72):
        middle = (low + high) / 2.0
        expected_rank = 1.0 + sum(
            _elo_probability(rating, middle)
            for rating in ratings
        )
        # Expected rank decreases as the hypothetical rating rises.
        if expected_rank > target_rank:
            low = middle
        else:
            high = middle
    return (low + high) / 2.0


def _midranks(values: list[float], *, descending: bool) -> list[float]:
    """Return average positions for ties, aligned to the original input."""
    order = sorted(
        range(len(values)),
        key=lambda index: values[index],
        reverse=descending,
    )
    result = [0.0] * len(values)
    start = 0
    while start < len(order):
        end = start
        value = values[order[start]]
        while end + 1 < len(order) and values[order[end + 1]] == value:
            end += 1
        midpoint = ((start + 1) + (end + 1)) / 2.0
        for position in range(start, end + 1):
            result[order[position]] = midpoint
        start = end + 1
    return result


def _top_rank_coordinate(rank: float, field_size: int) -> float:
    """Normalized logarithmic/DCG coordinate: rank 1 -> 1, rank N -> 0."""
    if field_size <= 1:
        return 0.0
    rank = min(float(field_size), max(1.0, float(rank)))
    tail = 1.0 / math.log2(field_size + 1.0)
    return (1.0 / math.log2(rank + 1.0) - tail) / (1.0 - tail)


def rank_weirdness_distance(
    predicted_rank: float,
    actual_rank: float,
    *,
    field_size: int,
) -> float:
    """Bounded rank displacement with strong emphasis on the front.

    The 75% logarithmic coordinate makes ``1 -> 40`` materially stranger than
    ``100 -> 200`` in a 200-team field, while the 25% linear component ensures
    that the whole standings still contribute.
    """
    if field_size <= 1:
        return 0.0
    predicted = min(float(field_size), max(1.0, float(predicted_rank)))
    actual = min(float(field_size), max(1.0, float(actual_rank)))
    linear = abs(actual - predicted) / (field_size - 1.0)
    top = abs(
        _top_rank_coordinate(actual, field_size)
        - _top_rank_coordinate(predicted, field_size)
    )
    return WEIRDNESS_LINEAR_SHARE * linear + WEIRDNESS_TOP_SHARE * top


def _team_upset_confidences(
    teams: list[MetricTeam],
    actual_midranks: list[float],
) -> list[float]:
    """Average Elo confidence over each team's realized ordering inversions."""
    confidence_sum = [0.0] * len(teams)
    inversion_count = [0] * len(teams)

    for i in range(len(teams)):
        for j in range(i + 1, len(teams)):
            if actual_midranks[i] == actual_midranks[j]:
                continue
            rating_i = teams[i].rating
            rating_j = teams[j].rating
            if rating_i == rating_j:
                continue
            predicted_i_better = rating_i > rating_j
            actual_i_better = actual_midranks[i] < actual_midranks[j]
            if predicted_i_better == actual_i_better:
                continue

            probability_i = _elo_probability(rating_i, rating_j)
            confidence = abs(2.0 * probability_i - 1.0)
            confidence_sum[i] += confidence
            inversion_count[i] += 1
            confidence_sum[j] += confidence
            inversion_count[j] += 1

    return [
        confidence_sum[i] / inversion_count[i] if inversion_count[i] else 0.0
        for i in range(len(teams))
    ]


def _weirdness(teams: list[MetricTeam]) -> float | None:
    """Compute weirdness over the caller's complete-history comparison field."""
    n = len(teams)
    if n < 2:
        return None

    ratings = [team.rating for team in teams]
    actual_values = [team.actual_rank for team in teams]
    predicted_midranks = _midranks(ratings, descending=True)
    actual_midranks = _midranks(actual_values, descending=False)
    confidences = _team_upset_confidences(teams, actual_midranks)

    distance_sum = 0.0
    for predicted, actual, confidence in zip(
        predicted_midranks,
        actual_midranks,
        confidences,
    ):
        distance = rank_weirdness_distance(
            predicted,
            actual,
            field_size=n,
        )
        confidence_multiplier = (
            1.0 - WEIRDNESS_CONFIDENCE_SHARE
            + WEIRDNESS_CONFIDENCE_SHARE * confidence
        )
        distance_sum += distance * confidence_multiplier

    value = 100.0 * distance_sum / n
    return min(100.0, max(0.0, value))


def compute_contest_metrics(
    teams: Iterable[MetricTeam],
    *,
    awards_medals: bool = True,
) -> dict:
    """Compute the full public metric document for one contest.

    Callers pass ``awards_medals=False`` for online preliminary rounds and for
    contests whose source data has no explicit medal rule. Medal cutoffs then
    become zero and the three medal difficulty values stay null, while top-3,
    top-10, overall, and weirdness continue to be calculated normally.
    Strength admits every official participating team at equal weight,
    including wholly unknown rosters. Weirdness uses only teams whose three
    members all have pre-contest official history.
    """
    strength_teams = _strength_candidates(teams)
    complete_teams = [
        team
        for team in strength_teams
        if team.known_members >= COMPLETE_HISTORY_MEMBER_COUNT
    ]
    zero_history_team_count = sum(
        team.known_members <= 0 for team in strength_teams
    )
    partial_history_team_count = sum(
        0 < team.known_members < COMPLETE_HISTORY_MEMBER_COUNT
        for team in strength_teams
    )
    history_coverage = (
        len(complete_teams) / len(strength_teams)
        if strength_teams
        else 0.0
    )
    n = len(strength_teams)
    awards_medals = bool(awards_medals)
    cutoffs = (
        medal_cutoffs(n)
        if awards_medals
        else {"gold": 0, "silver": 0, "bronze": 0}
    )
    empty_values = {key: None for key in _STRENGTH_KEYS}
    if n == 0:
        return {
            "version": "contest-metrics-v7",
            "awardsMedals": awards_medals,
            "effectiveTeamCount": 0,
            "zeroHistoryTeamCount": 0,
            "partialHistoryTeamCount": 0,
            "weirdnessTeamCount": 0,
            "historyCoverage": history_coverage,
            "medalCutoffs": cutoffs,
            "strength": dict(empty_values),
            "weirdness": None,
        }

    overall = sum(team.rating for team in strength_teams) / n
    strength = {
        "bronze": (
            _cutoff_rating(strength_teams, cutoffs["bronze"])
            if awards_medals
            else None
        ),
        "silver": (
            _cutoff_rating(strength_teams, cutoffs["silver"])
            if awards_medals
            else None
        ),
        "gold": (
            _cutoff_rating(strength_teams, cutoffs["gold"])
            if awards_medals
            else None
        ),
        "top3": _cutoff_rating(strength_teams, min(3, n)),
        "top10": _cutoff_rating(strength_teams, min(10, n)),
        "overall": overall,
    }
    weirdness_coverage = history_coverage
    weirdness = _weirdness(complete_teams)
    if weirdness is not None:
        # Missing roster history is missing evidence, not evidence of a normal
        # or surprising result. Partial teams are removed from the relative
        # rank comparison above, then their share of the effective field
        # proportionally lowers confidence in the contest-level score.
        weirdness *= weirdness_coverage

    return {
        "version": "contest-metrics-v7",
        "awardsMedals": awards_medals,
        "effectiveTeamCount": n,
        "zeroHistoryTeamCount": zero_history_team_count,
        "partialHistoryTeamCount": partial_history_team_count,
        "weirdnessTeamCount": len(complete_teams),
        "historyCoverage": history_coverage,
        "medalCutoffs": cutoffs,
        "strength": {
            key: round(float(value), 2) if value is not None else None
            for key, value in strength.items()
        },
        "weirdness": round(float(weirdness), 2) if weirdness is not None else None,
    }
