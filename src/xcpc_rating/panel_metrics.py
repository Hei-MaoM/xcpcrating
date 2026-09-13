"""Pure helpers for the five contest-panel metrics.

The SRK loader intentionally keeps the rating model small and discards raw
submission details.  The web exporter reads those details again and uses the
helpers in this module to derive the few display metrics that need timestamps
or per-problem attempts.  The functions are deliberately defensive: older or
partial boards may omit ``statuses`` and should produce missing values rather
than invented zeros.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any


_MINUTES_PER_UNIT = {
    "ms": 1.0 / 60_000.0,
    "millisecond": 1.0 / 60_000.0,
    "milliseconds": 1.0 / 60_000.0,
    "s": 1.0 / 60.0,
    "sec": 1.0 / 60.0,
    "second": 1.0 / 60.0,
    "seconds": 1.0 / 60.0,
    "m": 1.0,
    "min": 1.0,
    "minute": 1.0,
    "minutes": 1.0,
    "h": 60.0,
    "hr": 60.0,
    "hour": 60.0,
    "hours": 60.0,
}

# SRK uses ``FB`` (first blood) for an accepted submission that also earned
# the first-blood marker.  It is an AC for all five panel calculations.
_AC_RESULTS = {"AC", "FB"}


def _time_minutes(value: Any, *, default_unit: str) -> float | None:
    """Convert an SRK time value to minutes.

    SRK normally stores times as ``[number, unit]``.  A few historical boards
    use a bare number; callers choose the appropriate fallback unit explicitly
    (contest durations default to minutes, submission times to seconds).
    """

    unit = default_unit
    raw = value
    if isinstance(value, (list, tuple)):
        if not value:
            return None
        raw = value[0]
        if len(value) > 1 and value[1] is not None:
            unit = str(value[1]).strip().lower()
    try:
        number = float(raw)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number < 0:
        return None
    factor = _MINUTES_PER_UNIT.get(str(unit).strip().lower())
    if factor is None:
        return None
    return number * factor


def contest_duration_minutes(contest_meta: Mapping[str, Any]) -> float | None:
    """Return a contest's duration in minutes, or ``None`` when unavailable."""

    if not isinstance(contest_meta, Mapping):
        return None
    return _time_minutes(contest_meta.get("duration"), default_unit="min")


def supports_panel_metrics(raw_contest: Mapping[str, Any]) -> bool:
    """Whether a raw board uses ICPC solved-problem scoring.

    A small number of collection entries use points (``sorter.algorithm =
    score``). Their score value may be 700 or 900 and must never be presented
    as an AC count. Older boards without sorter metadata are admitted only when
    they contain both a problem list and per-problem statuses.
    """

    if not isinstance(raw_contest, Mapping):
        return False
    sorter = raw_contest.get("sorter")
    algorithm = sorter.get("algorithm") if isinstance(sorter, Mapping) else None
    if algorithm is not None:
        return str(algorithm).strip().upper() == "ICPC"
    problems = raw_contest.get("problems")
    rows = raw_contest.get("rows")
    return (
        isinstance(problems, Sequence)
        and not isinstance(problems, (str, bytes))
        and bool(problems)
        and isinstance(rows, Sequence)
        and not isinstance(rows, (str, bytes))
        and any(
            isinstance(row, Mapping)
            and isinstance(row.get("statuses"), Sequence)
            and not isinstance(row.get("statuses"), (str, bytes))
            for row in rows
        )
    )


def rank_percent(rank: Any, team_count: Any) -> float | None:
    """Return a one-based rank as a percentage of the comparison field."""

    try:
        rank_value = float(rank)
        count_value = float(team_count)
    except (TypeError, ValueError):
        return None
    if (
        not math.isfinite(rank_value)
        or not math.isfinite(count_value)
        or count_value <= 0
        or rank_value <= 0
    ):
        return None
    return rank_value / count_value * 100.0


def _result_is_ac(value: Any) -> bool:
    return str(value or "").strip().upper() in _AC_RESULTS


def _solution_entries(status: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    raw = status.get("solutions")
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return []
    return [item for item in raw if isinstance(item, Mapping)]


def _accepted_time_minutes(status: Mapping[str, Any]) -> float | None:
    """First accepted-submission time for one problem status."""

    accepted_times = [
        parsed
        for solution in _solution_entries(status)
        if _result_is_ac(solution.get("result"))
        for parsed in [_time_minutes(solution.get("time"), default_unit="s")]
        if parsed is not None
    ]
    if accepted_times:
        return min(accepted_times)
    if _result_is_ac(status.get("result")):
        return _time_minutes(status.get("time"), default_unit="s")
    return None


def _status_is_solved(status: Mapping[str, Any]) -> bool:
    return _accepted_time_minutes(status) is not None or _result_is_ac(
        status.get("result")
    )


def status_is_solved(status: Mapping[str, Any]) -> bool:
    """Return whether one raw SRK problem status contains an AC/FB result.

    The exporter uses the same defensive acceptance rules as the existing
    contest-panel metrics when building the type-skill profile.  Keeping this
    small public wrapper avoids duplicating the ``AC``/``FB`` and solution-list
    handling in a second module.
    """

    return isinstance(status, Mapping) and _status_is_solved(status)


def _wrong_attempts(status: Mapping[str, Any]) -> int:
    """Count wrong attempts before the first AC for a solved problem."""

    if not _status_is_solved(status):
        return 0
    solutions = _solution_entries(status)
    if solutions:
        wrong = 0
        for solution in solutions:
            if _result_is_ac(solution.get("result")):
                break
            wrong += 1
        return wrong

    # When a board omits the solution list, ``tries`` includes the eventual AC.
    try:
        tries = int(status.get("tries", 1))
    except (TypeError, ValueError):
        tries = 1
    return max(tries - 1, 0)


def extract_team_panel_metrics(
    raw_row: Mapping[str, Any],
    _problems: Sequence[Mapping[str, Any]] | None,
    duration_minutes: float | None,
) -> dict[str, float | int | None]:
    """Extract Dirt, first-AC time, and last-hour AC count for one team row.

    ``dirt`` is the user's requested ratio: wrong attempts on problems that
    eventually received an AC divided by the number of solved problems.  The
    result is ``None`` when the row has no usable per-problem status detail.
    ``last_hour_solved`` counts each solved problem once, using its first AC.
    """

    statuses_raw = raw_row.get("statuses") if isinstance(raw_row, Mapping) else None
    if not isinstance(statuses_raw, Sequence) or isinstance(statuses_raw, (str, bytes)):
        return {
            "dirt": None,
            "dirt_wrong_attempts": None,
            "dirt_solved": None,
            "first_a_minutes": None,
            "last_hour_solved": None,
        }
    statuses = [item for item in statuses_raw if isinstance(item, Mapping)]
    if not statuses:
        return {
            "dirt": None,
            "dirt_wrong_attempts": None,
            "dirt_solved": None,
            "first_a_minutes": None,
            "last_hour_solved": None,
        }

    solved_statuses = [status for status in statuses if _status_is_solved(status)]
    dirt_wrong_attempts = sum(_wrong_attempts(status) for status in solved_statuses)
    dirt_solved = len(solved_statuses)
    if solved_statuses:
        dirt = dirt_wrong_attempts / dirt_solved
    else:
        dirt = None

    accepted_times = [
        accepted
        for status in solved_statuses
        if (accepted := _accepted_time_minutes(status)) is not None
    ]
    first_a = min(accepted_times) if accepted_times else None

    last_hour = None
    if duration_minutes is not None and math.isfinite(duration_minutes):
        cutoff = max(duration_minutes - 60.0, 0.0)
        last_hour = sum(
            1
            for status in solved_statuses
            if (accepted := _accepted_time_minutes(status)) is not None
            and cutoff <= accepted <= duration_minutes
        )

    return {
        "dirt": dirt,
        "dirt_wrong_attempts": dirt_wrong_attempts,
        "dirt_solved": dirt_solved,
        "first_a_minutes": first_a,
        "last_hour_solved": last_hour,
    }


def history_panel_fields(
    *,
    tier: str,
    solved: Any,
    rank: Any,
    team_count: Any,
    extracted: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the stable JSON fields copied onto a player history row."""

    try:
        solved_value = int(solved)
    except (TypeError, ValueError):
        solved_value = 0

    def finite_or_none(value: Any) -> float | int | None:
        if value is None:
            return None
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(number):
            return None
        return value

    return {
        "tier": tier,
        "solved": solved_value,
        "rankPercent": rank_percent(rank, team_count),
        "dirt": finite_or_none(extracted.get("dirt")),
        "dirtWrong": finite_or_none(extracted.get("dirt_wrong_attempts")),
        "dirtSolved": finite_or_none(extracted.get("dirt_solved")),
        "firstATime": finite_or_none(extracted.get("first_a_minutes")),
        "lastHourSolved": finite_or_none(extracted.get("last_hour_solved")),
    }
