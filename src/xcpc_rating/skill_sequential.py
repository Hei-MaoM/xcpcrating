"""Chronological Bayesian updates for the seven problem-type abilities.

The state is an absolute rating in the same scale as the contest and problem
ratings.  A team result is an observation of every member, so callers should
split its weight between members before passing observations here.  The update
is a damped one-step Laplace update: a contest is predicted in full first and
then incorporated as one correlated information block.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Iterable, Mapping


SEQUENTIAL_SKILL_MODEL = "sequential-irt-v1"


@dataclass(frozen=True)
class SequentialSkillConfig:
    """Numerical controls for the chronological skill update."""

    prior_sd: float = 400.0
    learning_rate: float = 0.75
    process_sd_per_year: float = 60.0
    max_sd: float = 650.0
    contest_weight_cap: float = 1.0
    rank_z: float = 0.84


@dataclass
class SequentialSkillState:
    """Posterior state for one player and one problem type."""

    rating: float
    variance: float
    unique_problems: int = 0
    contests: int = 0
    information: float = 0.0
    last_at: str | None = None


def _sigmoid(value: float) -> float:
    if value >= 0:
        z = math.exp(-min(value, 745.0))
        return 1.0 / (1.0 + z)
    z = math.exp(max(value, -745.0))
    return z / (1.0 + z)


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _group_observations(
    observations: Iterable[Mapping[str, Any]],
) -> list[list[Mapping[str, Any]]]:
    """Group observations by contest while retaining chronological order."""

    groups: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    order: list[tuple[str, str]] = []
    for index, raw in enumerate(observations):
        if not isinstance(raw, Mapping):
            continue
        contest = str(raw.get("contestId") or f"__row_{index}")
        at = str(raw.get("contestStartAt") or "")
        key = (contest, at)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(raw)

    # Exported evidence carries contestStartAt.  Sorting only when every group
    # has a parseable timestamp keeps old fixtures deterministic and avoids
    # inventing an order for legacy records without dates.
    if order and all(_parse_time(at) is not None for _, at in order):
        order.sort(key=lambda key: (_parse_time(key[1]), key[0]))
    return [groups[key] for key in order]


def _advance_variance(
    state: SequentialSkillState,
    event_at: str | None,
    config: SequentialSkillConfig,
) -> None:
    if not state.last_at or not event_at:
        return
    previous = _parse_time(state.last_at)
    current = _parse_time(event_at)
    if previous is None or current is None:
        return
    years = max(0.0, (current - previous).total_seconds() / (365.25 * 86400.0))
    process_variance = (max(0.0, config.process_sd_per_year) * years) ** 2
    state.variance = min(
        max(config.prior_sd * config.prior_sd, state.variance + process_variance),
        config.max_sd * config.max_sd,
    )


def _number(raw: Any, default: float) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return default
    return value if math.isfinite(value) else default


def update_sequential_skill(
    observations: Iterable[Mapping[str, Any]],
    *,
    config: SequentialSkillConfig = SequentialSkillConfig(),
    baseline_rating: float | None = None,
    initial_state: SequentialSkillState | None = None,
    offset_fn: Callable[[Mapping[str, Any]], float | None] | None = None,
) -> tuple[SequentialSkillState, dict[str, float | int | None]]:
    """Replay observations in time order and return the posterior state.

    Each observation must provide ``solved``, ``problemRating`` and either
    ``playerPreRating`` or ``teamPreRating``.  ``offset_fn`` converts one row
    into the baseline log-odds at the pre-contest rating; the default derives
    it from the absolute ratings.  A failed unexpectedly hard problem has a
    naturally tiny gradient (``-p``), while a hard success has a large one
    (``1-p``); no outcome-dependent multiplier is used, so the update remains
    calibrated and cannot inflate scores merely by changing asymmetry.
    """

    if config.prior_sd <= 0 or config.max_sd < config.prior_sd:
        raise ValueError("invalid sequential skill uncertainty configuration")
    if not 0 < config.learning_rate <= 1:
        raise ValueError("learning_rate must be in (0, 1]")
    if config.contest_weight_cap <= 0:
        raise ValueError("contest_weight_cap must be positive")

    rows = [
        raw for raw in observations
        if isinstance(raw, Mapping) and raw.get("solved") is not None
    ]
    if initial_state is None:
        first_rating = baseline_rating
        if first_rating is None and rows:
            first_rating = _number(
                rows[0].get("playerPreRating", rows[0].get("teamPreRating")),
                1700.0,
            )
        if first_rating is None:
            first_rating = 1700.0
        state = SequentialSkillState(
            rating=first_rating,
            variance=config.prior_sd * config.prior_sd,
        )
    else:
        state = initial_state

    groups = _group_observations(rows)
    total_weight = 0.0
    expected_total = 0.0
    for group in groups:
        event_at = next(
            (str(row.get("contestStartAt")) for row in group if row.get("contestStartAt")),
            None,
        )
        _advance_variance(state, event_at, config)
        weights = [max(0.0, _number(row.get("weight", row.get("evidenceWeight", 1.0)), 1.0)) for row in group]
        total = sum(weights)
        if total <= 0:
            continue
        scale = min(1.0, config.contest_weight_cap / total)
        gradient = 0.0
        information = 0.0
        group_weight = 0.0
        for row, raw_weight in zip(group, weights):
            weight = raw_weight * scale
            problem = _number(row.get("problemRating"), 1700.0)
            discrimination = max(0.05, _number(row.get("problemDiscrimination", 1.0), 1.0))
            # The rating scale is Elo-like.  The optional callback also lets
            # the problem_types module include team/problem uncertainty.
            if offset_fn is None:
                baseline = _number(
                    row.get("playerPreRating", row.get("teamPreRating")),
                    state.rating,
                )
                offset = math.log(10.0) / 400.0 * discrimination * (baseline - problem)
            else:
                offset = offset_fn(row)
                if offset is None:
                    continue
            load = math.log(10.0) / 400.0 * discrimination
            probability = _sigmoid(offset + load * (state.rating - _number(
                row.get("playerPreRating", row.get("teamPreRating")),
                state.rating,
            ))) if offset_fn is not None else _sigmoid(offset + load * (state.rating - _number(
                row.get("playerPreRating", row.get("teamPreRating")), state.rating
            )))
            # With the default offset, the expression above simplifies to the
            # absolute current axis rating.  With a calibrated callback the
            # same state is interpreted as a residual around that baseline.
            y = 1.0 if bool(row.get("solved")) else 0.0
            gradient += weight * load * (y - probability)
            information += weight * load * load * probability * (1.0 - probability)
            group_weight += weight
            expected_total += weight * probability

        if information > 0 and group_weight > 0:
            prior_precision = 1.0 / state.variance
            posterior_precision = prior_precision + config.learning_rate * information
            posterior_variance = min(
                config.max_sd * config.max_sd,
                1.0 / posterior_precision,
            )
            state.rating += config.learning_rate * posterior_variance * gradient
            state.variance = posterior_variance
            state.information += information
            total_weight += group_weight
        if group_weight > 0:
            # Counts describe observed classified problems, including an
            # outcome whose expected information is numerically negligible.
            # They are diagnostics and public sample gates must use this real
            # count rather than an effective-weight approximation.
            state.unique_problems += len(group)
            state.contests += 1
        if event_at:
            state.last_at = event_at

    posterior_sd = math.sqrt(max(state.variance, 0.0))
    lower = state.rating - config.rank_z * posterior_sd
    baseline_probability = expected_total / total_weight if total_weight else None
    return state, {
        "ability": state.rating,
        "displayMastery": max(0.0, min(1.0, (state.rating - 1000.0) / 2000.0)),
        "posteriorSd": posterior_sd,
        "lowerBound": lower,
        "expectedMastery": baseline_probability,
        "effectiveWeight": total_weight,
        "information": state.information,
        "confidence": max(0.0, min(1.0, state.information * state.variance)),
        "uniqueProblems": state.unique_problems,
        "contests": state.contests,
    }
