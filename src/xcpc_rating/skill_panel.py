"""Seven-axis problem-type skill panels.

The type manifest is deliberately kept separate from player shards.  This
module only turns transient, team-level problem evidence into a compact
per-player/per-tier profile; it does not fetch QOJ pages or infer labels.
"""

from __future__ import annotations

import math
from bisect import bisect_left, bisect_right
from collections.abc import Iterable, Mapping
from typing import Any

from .problem_types import (
    PROBLEM_TYPE_AXES,
    aggregate_skill_mastery,
    aggregate_skill_mastery_sequential,
)


SKILL_MIN_COVERAGE = 0.6
# Kept as a compatibility/documentation constant; it is no longer a hard
# ranking gate.  Small samples are shown with conservative shrinkage instead.
SKILL_MIN_UNIQUE_PROBLEMS = 3
SKILL_PRIOR = 0.5
SKILL_PRIOR_STRENGTH = 2.0
SKILL_WILSON_Z = 0.84
SKILL_SCORE_MODEL = "sequential-irt-v1"
SKILL_GRADE_CUTOFFS = ((1.0, "S"), (5.0, "A"), (15.0, "B"), (35.0, "C"),
                       (60.0, "D"), (85.0, "E"))


def _top_percent(value: float, ordered: list[float]) -> float:
    """Return a mid-rank percentile where 0 is best."""

    if not ordered:
        return 100.0
    left = bisect_left(ordered, value)
    right = bisect_right(ordered, value)
    better = len(ordered) - right
    ties = right - left
    return (better + ties * 0.5) / len(ordered) * 100.0


def _competition_ranks(scores: Mapping[str, float]) -> dict[str, int]:
    ordered = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    ranks: dict[str, int] = {}
    previous: float | None = None
    previous_rank = 0
    for index, (key, score) in enumerate(ordered, start=1):
        if previous is None or score != previous:
            previous_rank = index
        ranks[key] = previous_rank
        previous = score
    return ranks


def _grade(top_percent: float | None, rank: int | None, *, stable: bool = True) -> str | None:
    if stable and rank == 1:
        return "SSS"
    if stable and rank is not None and 2 <= rank <= 10:
        return "SS"
    if top_percent is None or not math.isfinite(top_percent):
        return None
    value = min(max(top_percent, 0.0), 100.0)
    for cutoff, grade in SKILL_GRADE_CUTOFFS:
        if value <= cutoff:
            return grade
    return "F"


def _axis_eligible(aggregate: Mapping[str, Any], axis: str) -> bool:
    item = aggregate["axes"][axis]
    return item.get("mastery") is not None and float(item.get("effectiveProblems", 0.0)) > 0


def _axis_metrics(
    aggregate: Mapping[str, Any],
    axis: str,
    *,
    allow_established_raw: bool = True,
    use_calibrated: bool = True,
) -> dict[str, Any]:
    """Derive display/ranking values with small-sample protection.

    Current taxonomies use the offset-IRT posterior prepared by
    :func:`aggregate_skill_mastery`.  ``v1`` exports retain the legacy Wilson
    path so old fixtures and previously published bundles remain readable.
    """
    item = aggregate["axes"][axis]
    raw = item.get("rawMastery", item.get("mastery"))
    if raw is None:
        return {"displayMastery": None, "rankScore": None, "confidence": 0.0, "evidenceLevel": "missing"}
    raw = min(max(float(raw), 0.0), 1.0)
    sequential = item.get("scoreModel") == SKILL_SCORE_MODEL
    if use_calibrated and sequential and item.get("ability") is not None:
        unique = float(item.get("uniqueProblems", 0.0))
        coverage = min(max(float(aggregate.get("coverage", 0.0)), 0.0), 1.0)
        display = min(max(float(item.get("mastery", 0.5)), 0.0), 1.0)
        # Keep original rating points, including values outside 1000--3000.
        # Posterior SD is diagnostic and never lowers the public ranking score.
        rank_score = float(item["ability"])
        evidence_level = (
            "established" if unique >= 3 and coverage >= SKILL_MIN_COVERAGE
            else "provisional" if unique >= 1
            else "exploratory"
        )
        return {
            "displayMastery": display,
            "rankScore": rank_score,
            "confidence": min(
                max(float(item.get("modelConfidence", 0.0)), 0.0), 1.0
            ),
            "effectiveProblems": float(item.get("effectiveProblems", 0.0)),
            "evidenceLevel": evidence_level,
            "rankEligible": True,
        }
    n_axis = float(item.get("effectiveProblems", item.get("uniqueProblems", 0.0)))
    coverage = min(max(float(aggregate.get("coverage", 0.0)), 0.0), 1.0)
    axis_coverage = min(max(float(item.get("axisCoverage", coverage)), 0.0), 1.0)
    n_eff = n_axis * axis_coverage
    if (
        use_calibrated
        and item.get("abilityLowerBound") is not None
        and n_axis > 0
        and float(item.get("modelConfidence", 0.0)) > 0
    ):
        display = min(max(float(item.get("mastery", 0.5)), 0.0), 1.0)
        rank_score = min(max(float(item["abilityLowerBound"]), 0.0), 1.0)
        evidence_level = (
            "established" if n_axis >= 3 and coverage >= SKILL_MIN_COVERAGE
            else "provisional" if n_axis >= 1
            else "exploratory"
        )
        return {
            "displayMastery": display,
            "rankScore": rank_score,
            "confidence": min(
                max(float(item.get("modelConfidence", 0.0)) * axis_coverage, 0.0),
                1.0,
            ),
            "effectiveProblems": n_axis,
            "evidenceLevel": evidence_level,
            "rankEligible": True,
        }
    # Established evidence may retain the intuitive weighted solve rate.  Less
    # evidence is pulled toward a neutral cohort prior, so one AC is not 100.
    if allow_established_raw and n_axis >= SKILL_MIN_UNIQUE_PROBLEMS and coverage >= SKILL_MIN_COVERAGE:
        display = raw
    else:
        display = (raw * n_eff + SKILL_PRIOR_STRENGTH * SKILL_PRIOR) / (
            n_eff + SKILL_PRIOR_STRENGTH
        )
    if n_eff <= 0:
        rank_score = None
    else:
        z = SKILL_WILSON_Z
        denom = 1.0 + z * z / n_eff
        center = (raw + z * z / (2.0 * n_eff)) / denom
        margin = z * math.sqrt(
            raw * (1.0 - raw) / n_eff + z * z / (4.0 * n_eff * n_eff)
        ) / denom
        rank_score = max(0.0, min(1.0, center - margin))
    evidence_level = (
        "established" if n_axis >= 3 and coverage >= 0.6
        else "provisional" if n_axis >= 1
        else "exploratory"
    )
    return {
        "displayMastery": display,
        "rankScore": rank_score,
        "confidence": n_eff / (n_eff + SKILL_PRIOR_STRENGTH),
        "effectiveProblems": n_axis,
        "evidenceLevel": evidence_level,
        "rankEligible": True,
    }


def _valid_contests(evidence: Iterable[Mapping[str, Any]]) -> int:
    return len({str(item.get("contestId")) for item in evidence if item.get("contestId")})


def build_player_skill_panels(
    records: dict[str, dict[str, Any]],
    evidence_by_player: Mapping[str, Iterable[Mapping[str, Any]]],
    *,
    taxonomy_version: str,
) -> None:
    """Attach verbose ``skillPanel`` payloads to player records in-place.

    Evidence entries are team-level samples carrying ``tier``, ``official``,
    ``contestId``, ``canonicalId``, ``labels``, ``difficultyWeight`` and
    ``solved``.  The function computes per-axis cohort percentiles only after
    cross-contest canonical-id deduplication.
    """

    for mode, official_only in (("all", False), ("official", True)):
        for tier in ("overall",):
            aggregates: dict[str, dict[str, Any]] = {}
            scoped_evidence: dict[str, list[Mapping[str, Any]]] = {}
            for player_key in records:
                scoped = [
                    item
                    for item in evidence_by_player.get(player_key, ())
                    if (tier == "overall" or item.get("tier") == tier)
                    and (not official_only or item.get("official", True) is True)
                ]
                if not scoped:
                    continue
                scoped_evidence[player_key] = scoped
                aggregates[player_key] = (
                    aggregate_skill_mastery(scoped)
                    if str(taxonomy_version).startswith("v1")
                    else aggregate_skill_mastery_sequential(scoped)
                )
            if not aggregates:
                continue

            cohorts: dict[str, list[float]] = {axis: [] for axis in PROBLEM_TYPE_AXES}
            smooth_display = not str(taxonomy_version).startswith("v1")
            for aggregate in aggregates.values():
                for axis in PROBLEM_TYPE_AXES:
                    derived = _axis_metrics(
                        aggregate,
                        axis,
                        allow_established_raw=not smooth_display,
                        use_calibrated=smooth_display,
                    )
                    if derived["rankScore"] is not None:
                        cohorts[axis].append(float(derived["rankScore"]))
            for values in cohorts.values():
                values.sort()

            # Keep the competition rank alongside the percentile.  Percentiles
            # become indistinguishable at the top once rounded to two decimal
            # places, while the rank remains an exact, actionable value for
            # the player dossier.
            ranks_by_axis: dict[str, dict[str, int]] = {}
            for axis in PROBLEM_TYPE_AXES:
                scores: dict[str, float] = {}
                for player_key, aggregate in aggregates.items():
                    rank_score = _axis_metrics(
                        aggregate,
                        axis,
                        allow_established_raw=not smooth_display,
                        use_calibrated=smooth_display,
                    )["rankScore"]
                    if rank_score is not None:
                        scores[player_key] = float(rank_score)
                ranks_by_axis[axis] = _competition_ranks(scores)

            for player_key, aggregate in aggregates.items():
                axes: dict[str, dict[str, Any]] = {}
                for axis in PROBLEM_TYPE_AXES:
                    raw = aggregate["axes"][axis]
                    derived = _axis_metrics(
                        aggregate,
                        axis,
                        allow_established_raw=not smooth_display,
                        use_calibrated=smooth_display,
                    )
                    eligible = derived["rankScore"] is not None
                    mastery = (
                        float(derived["displayMastery"])
                        if derived["displayMastery"] is not None else None
                    )
                    rank_score = derived["rankScore"]
                    original_rating = raw.get("scoreModel") == SKILL_SCORE_MODEL
                    if eligible and rank_score is not None:
                        top_percent = _top_percent(float(rank_score), cohorts[axis])
                        score = float(raw["ability"]) if original_rating else mastery * 100.0
                    else:
                        top_percent = None
                        score = None
                    axes[axis] = {
                        "score": round(score, 2) if score is not None else None,
                        "mastery": round(mastery, 6) if mastery is not None else None,
                        "rawMastery": round(float(raw.get("rawMastery", raw.get("mastery"))), 6) if raw.get("mastery") is not None else None,
                        "rankScore": (
                            round(float(rank_score), 6) if original_rating
                            else round(float(rank_score) * 100.0, 2)
                        ) if rank_score is not None else None,
                        "topPercent": round(top_percent, 2) if top_percent is not None else None,
                        "rank": ranks_by_axis[axis].get(player_key),
                        "grade": None,
                        "coverage": round(float(aggregate.get("coverage", 0.0)), 4),
                        "axisCoverage": round(float(raw.get("axisCoverage", aggregate.get("coverage", 0.0))), 4),
                        "uniqueProblems": int(raw.get("uniqueProblems", 0)),
                        "successWeight": round(float(raw.get("successWeight", 0.0)), 4),
                        "exposureWeight": round(float(raw.get("exposureWeight", 0.0)), 4),
                        "validContests": _valid_contests(scoped_evidence[player_key]),
                        "effectiveProblems": round(float(derived.get("effectiveProblems", 0.0)), 3),
                        "confidence": round(float(derived.get("confidence", 0.0)), 4),
                        "evidenceLevel": derived.get("evidenceLevel", "missing"),
                        "rankEligible": bool(derived.get("rankEligible", False)),
                        "expectedMastery": (
                            round(float(raw["expectedMastery"]), 6)
                            if raw.get("expectedMastery") is not None else None
                        ),
                        "ability": (
                            round(float(raw["ability"]), 6)
                            if raw.get("ability") is not None else None
                        ),
                        "posteriorSd": (
                            round(float(raw["posteriorSd"]), 6)
                            if raw.get("posteriorSd") is not None else None
                        ),
                    }

                skill_panel = records[player_key].setdefault("skillPanel", {})
                mode_payload = skill_panel.setdefault(mode, {})
                mode_payload[tier] = {
                    "taxonomyVersion": taxonomy_version,
                    "scoreModel": SKILL_SCORE_MODEL if smooth_display else "legacy-wilson-v1",
                    "scoreScale": "rating" if smooth_display else "percent",
                    "contests": _valid_contests(scoped_evidence[player_key]),
                    "coverage": round(float(aggregate.get("coverage", 0.0)), 4),
                    "classifiedExposure": round(float(aggregate.get("classifiedExposure", 0.0)), 4),
                    "unknownExposure": round(float(aggregate.get("unknownExposure", 0.0)), 4),
                    "uniqueProblems": int(aggregate.get("uniqueProblems", 0)),
                    "axes": axes,
                }

            # Assign single-axis SSS/SS after all player aggregates in the cohort
            # are available.  A tie at the top shares rank 1 and therefore SSS.
            for axis in PROBLEM_TYPE_AXES:
                ranks = ranks_by_axis[axis]
                for player_key in ranks:
                    metric = records[player_key]["skillPanel"][mode][tier]["axes"][axis]
                    # The competitive badge is purely positional.  Evidence
                    # size remains visible as metadata, but college-only
                    # careers are too short to make a hard stability gate fair.
                    metric["grade"] = _grade(metric["topPercent"], ranks.get(player_key))


def compact_player_skill_panels(records: dict[str, dict[str, Any]]) -> None:
    """Convert verbose skill axes into the fixed-order shard wire format."""

    for record in records.values():
        panel = record.get("skillPanel")
        if not isinstance(panel, Mapping):
            continue
        compact_panel: dict[str, dict[str, Any]] = {}
        for mode in ("all", "official"):
            tiers = panel.get(mode)
            if not isinstance(tiers, Mapping):
                continue
            compact_tiers: dict[str, Any] = {}
            for tier, value in tiers.items():
                if not isinstance(value, Mapping):
                    continue
                raw_axes = value.get("axes", {})
                compact_axes = []
                for axis in PROBLEM_TYPE_AXES:
                    metric = raw_axes.get(axis, {}) if isinstance(raw_axes, Mapping) else {}
                    compact_axes.append([
                        metric.get("score"),
                        metric.get("mastery"),
                        metric.get("topPercent"),
                        metric.get("grade"),
                        metric.get("coverage", 0.0),
                        metric.get("uniqueProblems", 0),
                        metric.get("successWeight", 0.0),
                        metric.get("exposureWeight", 0.0),
                        metric.get("validContests", 0),
                        metric.get("rankScore"),
                        metric.get("rawMastery"),
                        metric.get("effectiveProblems", 0.0),
                        metric.get("confidence", 0.0),
                        metric.get("evidenceLevel", "missing"),
                        metric.get("rankEligible", False),
                        metric.get("expectedMastery"),
                        metric.get("ability"),
                        metric.get("posteriorSd"),
                        metric.get("rank"),
                        metric.get("axisCoverage", metric.get("coverage", 0.0)),
                    ])
                compact_tiers[tier] = {
                    "taxonomyVersion": value.get("taxonomyVersion", "problem-types-v1"),
                    "scoreModel": value.get("scoreModel", "legacy-wilson-v1"),
                    "scoreScale": value.get("scoreScale", "percent"),
                    "contests": value.get("contests", 0),
                    "coverage": value.get("coverage", 0.0),
                    "classifiedExposure": value.get("classifiedExposure", 0.0),
                    "unknownExposure": value.get("unknownExposure", 0.0),
                    "uniqueProblems": value.get("uniqueProblems", 0),
                    "axes": compact_axes,
                }
            if compact_tiers:
                compact_panel[mode] = compact_tiers
        if compact_panel:
            record["skillPanel"] = compact_panel
        else:
            record.pop("skillPanel", None)
