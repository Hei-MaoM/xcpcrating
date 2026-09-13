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
import math
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from itertools import groupby
from collections.abc import Mapping


def _git_head(path):
    """Return the source checkout commit when the input is a git worktree."""
    try:
        return subprocess.check_output(
            ["git", "-C", os.fspath(path), "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"

from . import perf
from .contest_metrics import MetricTeam, compute_contest_metrics
from .engines.incremental import INITIAL_EXPECT as PRIOR_MU
from .engines.incremental import (
    UNRATED_CONTESTS,
    IncrementalEngine,
    display_score,
    rerank_1224,
)
from .engines.school import SchoolEngine
from .identity import clean_org, display_name, resolve_i18n
from .loader import SRK_SUFFIX, LoadResult, SkippedContest, _is_online_prelim, load_contests, parse_contest
from .medals import MEDAL_COLORS, collect_medal_contest_ids, collect_medals
from .panel_metrics import (
    contest_duration_minutes,
    extract_team_panel_metrics,
    history_panel_fields,
    rank_percent,
    status_is_solved,
    supports_panel_metrics,
)
from .problem_types import (
    PROBLEM_TYPE_AXES,
    build_contest_problem_overview,
    build_problem_rating_index,
    difficulty_level_from_problem_rating,
    smoothed_solve_rate,
    smooth_difficulty_weight,
    validate_problem_manifest,
)

# For the public problem difficulty definition, a participating team that did
# not solve a problem is a failed observation, regardless of whether it made a
# submission.  This keeps the rating denominator aligned with AC / eligible
# teams and avoids rating a hard problem from submitters alone.
_PROBLEM_NO_ATTEMPT_WEIGHT = 1.0
from .skill_panel import (
    SKILL_MIN_COVERAGE,
    SKILL_MIN_UNIQUE_PROBLEMS,
    SKILL_SCORE_MODEL,
    build_player_skill_panels,
    compact_player_skill_panels,
)
from .prediction import build_predictions, prediction_index_entry
from .tier import classify_tier
from .validate import pairwise_concordance_for_teams

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

# Leaderboard pages are the exact size rendered by the frontend. The initial
# route therefore downloads one page instead of the complete 50k+ player board.
LEADERBOARD_PAGE_SIZE = 100

# The type leaderboard is a deliberately small, independent index.  It keeps
# the player shards useful for detail pages while allowing the leaderboard page
# to load one JSON document instead of scanning all 256 player shards.
SKILL_LEADERBOARD_INDEX_VERSION = "skill-leaderboards-v3"
SKILL_LEADERBOARD_ROW_FIELDS = (
    "rank",
    "key",
    "name",
    "org",
    "score",
    "topPercent",
    "grade",
    "uniqueProblems",
    "coverage",
    "rankScore",
    "effectiveProblems",
    "evidenceLevel",
    "confidence",
)

# A single-axis board is ordered by ``rankScore`` (the rank is the row index),
# so it ships the same fields minus the redundant ``rank`` column.
SKILL_LEADERBOARD_AXIS_FIELDS = tuple(
    field for field in SKILL_LEADERBOARD_ROW_FIELDS if field != "rank"
)

# Default I/O, resolved relative to the repo root (this file lives at
# src/xcpc_rating/export_web.py). Source data is a git submodule
# (vendor/srk-collection); update it via scripts/update_data.sh.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_DATA = os.path.join(_REPO_ROOT, "vendor", "srk-collection", "official")
DEFAULT_OUT = os.path.join(_REPO_ROOT, "web", "public", "data")
DEFAULT_PROBLEM_TYPES = os.path.join(
    _REPO_ROOT, "data", "problem-types", "2023-present-all-qoj-v2.json"
)
DEFAULT_PROBLEM_CATALOG = os.path.join(
    _REPO_ROOT, "data", "problem-catalog.json"
)
PREDICTION_SPECS = os.path.join(_REPO_ROOT, "predictions")

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


def _raw_contest_data(data_root: str, contest_id: str) -> dict:
    """Read one raw SRK contest payload for display/metric extraction."""

    path = os.path.join(data_root, contest_id + SRK_SUFFIX)
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    return data if isinstance(data, dict) else {}


def _load_problem_type_manifest(path: str | None) -> dict:
    """Load and validate the curated problem-type manifest.

    A missing/empty path is a supported mode for legacy exports: the replay
    still records unknown problem exposure, but no axis receives a guessed
    label.  Validation happens before any expensive contest replay.
    """

    if not path:
        return {"version": "problem-types-none", "axes": [], "problems": {}}
    if not os.path.isfile(path):
        raise FileNotFoundError(f"problem type manifest not found: {path}")
    with open(path, "r", encoding="utf-8") as handle:
        manifest = json.load(handle)
    validate_problem_manifest(manifest)
    return manifest


# Fields that exist only to document the review (two independent reviewers per
# field, their evidence and the root adjudication).  They are kept in the audit
# store under ``data/`` but never shipped to the web bundle: the published copy
# carries the final classification only, which keeps the asset ~15x smaller and
# free of audit provenance.
AUDIT_ONLY_PROBLEM_FIELDS = ("review", "evidence", "unresolvedEvidence")


def published_problem_manifest(manifest: Mapping[str, Any]) -> dict:
    """Return the manifest as published to the site (final values only)."""

    problems = manifest.get("problems") if isinstance(manifest, Mapping) else None
    if not isinstance(problems, Mapping):
        return dict(manifest) if isinstance(manifest, Mapping) else {}
    lean = dict(manifest)
    lean["problems"] = {
        str(key): {
            field: value
            for field, value in record.items()
            if field not in AUDIT_ONLY_PROBLEM_FIELDS
        }
        if isinstance(record, Mapping)
        else record
        for key, record in problems.items()
    }
    return lean


def _load_problem_catalog(path: str | None) -> dict:
    """Load the optional problem title/link catalog used by web exports.

    The catalog is keyed by the stable ``contest-id:alias`` identity.  Empty
    or missing paths deliberately disable enrichment so legacy/custom exports
    can still run from only the raw SRK collection.
    """

    if not path:
        return {"version": "problem-catalog-none", "problems": {}}
    if not os.path.isfile(path):
        # The catalog is an enrichment layer.  Raw rows still provide direct
        # links (and contest fallbacks), so a custom/legacy checkout without
        # this optional file should remain exportable.
        return {"version": "problem-catalog-none", "problems": {}}
    with open(path, "r", encoding="utf-8") as handle:
        catalog = json.load(handle)
    if not isinstance(catalog, Mapping):
        raise ValueError("problem catalog must be a JSON object")
    problems = catalog.get("problems", {})
    if not isinstance(problems, Mapping):
        raise ValueError("problem catalog 'problems' must be an object")
    # Keep only object records.  Invalid rows should not make an otherwise
    # usable export fail, and the problem overview treats absent rows as empty.
    catalog["problems"] = {
        str(key): value for key, value in problems.items() if isinstance(value, Mapping)
    }
    return dict(catalog)


def _manifest_problem(manifest: Mapping[str, object], contest_id: str, alias: str):
    problems = manifest.get("problems", {})
    if not isinstance(problems, Mapping):
        return None
    return problems.get(f"{contest_id}:{alias}")


def _skill_problem_evidence(
    *,
    contest_id: str,
    contest_start_at: str | None = None,
    tier: str,
    official: bool,
    raw_rows: list[dict],
    raw_row: Mapping[str, object],
    raw_problems: list[dict],
    manifest: Mapping[str, object],
    team_pre_rating: float | None = None,
    player_pre_rating: float | None = None,
    team_rating_sd: float | None = None,
    evidence_weight: float = 1.0,
    observed_status_counts: list[int] | None = None,
) -> list[dict]:
    """Build one team's type evidence list from aligned SRK statuses.

    The contest statistics calibrate the expected solve rate only.  A player's
    own solve flag comes exclusively from that team's aligned status entry; a
    missing entry is unknown rather than an implicit failed solve.  Evidence is
    namespaced by ``contest_id:alias`` so an accidental QOJ canonical-ID reuse
    cannot merge two unrelated contest opportunities.
    """

    if not raw_problems:
        return []
    try:
        evidence_weight = float(evidence_weight)
    except (TypeError, ValueError):
        evidence_weight = 1.0
    if not math.isfinite(evidence_weight) or evidence_weight <= 0:
        evidence_weight = 1.0
    # The status array is positionally aligned with the raw problem list.
    statuses = raw_row.get("statuses") if isinstance(raw_row, Mapping) else []
    if not isinstance(statuses, list):
        statuses = []

    if observed_status_counts is None:
        observed_status_counts = [0] * len(raw_problems)
        for row in raw_rows:
            row_statuses = row.get("statuses") if isinstance(row, Mapping) else None
            if not isinstance(row_statuses, list):
                continue
            for index in range(min(len(row_statuses), len(raw_problems))):
                if isinstance(row_statuses[index], Mapping):
                    observed_status_counts[index] += 1

    result = []
    for index, problem in enumerate(raw_problems):
        if not isinstance(problem, Mapping):
            continue
        alias = str(problem.get("alias") or index)
        status_observed = (
            index < len(statuses) and isinstance(statuses[index], Mapping)
        )
        status = statuses[index] if status_observed else {}
        curated = _manifest_problem(manifest, contest_id, alias)
        stats = problem.get("statistics") if isinstance(problem.get("statistics"), Mapping) else {}
        try:
            accepted = float(stats.get("accepted", 0))
        except (TypeError, ValueError):
            accepted = 0.0
        if not math.isfinite(accepted):
            accepted = 0.0
        # A problem can have fewer aligned statuses than the contest-wide row
        # count in partially recovered data.  Use the observed count, but never
        # let an authoritative accepted statistic make the rate invalid.
        observed_teams = observed_status_counts[index]
        eligible_teams = max(observed_teams, int(math.ceil(max(accepted, 0.0))), 1)
        accepted = min(max(accepted, 0.0), float(eligible_teams))
        try:
            expected_rate = smoothed_solve_rate(
                accepted=accepted, eligible_teams=eligible_teams
            )
            difficulty = smooth_difficulty_weight(
                accepted=accepted, eligible_teams=eligible_teams
            )
        except ValueError:
            expected_rate = 0.5
            difficulty = 1.0
        if isinstance(curated, Mapping):
            # Keep the fallback identity identical to the problem-rating fit
            # below so unclassified problems still receive their fitted
            # rating in the seven-dimension evidence panel.
            canonical_id = str(curated.get("canonicalId") or f"{contest_id}:{alias}")
            labels = curated.get("labels", {})
            status_name = curated.get("status", "unknown")
        else:
            canonical_id = f"{contest_id}:{alias}"
            labels = {}
            status_name = "unknown"
        if not status_observed:
            status_name = "unknown"
        result.append(
            {
                "contestId": contest_id,
                "contestStartAt": contest_start_at,
                "tier": tier,
                "official": official,
                "canonicalId": canonical_id,
                "identityKey": f"{contest_id}:{alias}",
                "labels": labels if isinstance(labels, Mapping) else {},
                "status": status_name,
                "classificationConfidence": (
                    float(curated.get("confidence", 1.0))
                    if isinstance(curated, Mapping) else 0.0
                ),
                "difficultyWeight": difficulty,
                "expectedSolveRate": expected_rate,
                "teamPreRating": team_pre_rating,
                "playerPreRating": player_pre_rating,
                "teamRatingSd": team_rating_sd,
                "evidenceWeight": evidence_weight,
                "statusObserved": status_observed,
                "solved": status_is_solved(status) if status_observed else None,
            }
        )
    return result


def _raw_team_rows(data_root: str, contest_id: str) -> list[dict]:
    """Re-read a contest's raw srk.json rows to recover team display fields.

    The loader keeps a 1:1 row->team mapping in standings order but discards the
    team's display name / org (it only persists members). We re-read the source
    file purely to recover ``name`` / ``org`` for the contest detail view; the
    rows are returned positionally aligned with ``Contest.teams``.
    """
    return _raw_contest_data(data_root, contest_id).get("rows", []) or []


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

    __slots__ = ("key", "name", "org", "history", "skill_evidence")

    def __init__(self, key: str, name: str, org: str) -> None:
        self.key = key
        self.name = name
        self.org = org
        self.history: list[dict] = []
        self.skill_evidence: list[dict] = []


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


def _team_rating_sd(engine: IncrementalEngine, team) -> float | None:
    """Conservative uncertainty proxy used only by the seven-axis model."""

    if not team.members:
        return None
    counts = []
    for member in team.members:
        state = engine._players.get(member.key)  # noqa: SLF001 - read-only snapshot
        if state is not None:
            try:
                counts.append(max(0.0, float(state.get("contests", 0))))
            except (TypeError, ValueError):
                counts.append(0.0)
    if not counts or max(counts) <= 0:
        return 400.0
    history = sum(counts) / len(counts)
    return max(100.0, min(400.0, 400.0 / math.sqrt(max(history, 1.0))))


def _team_skill_member_weights(engine: IncrementalEngine, team) -> list[float]:
    """Split one team-level outcome into conservative member evidence.

    The source data contains a solve flag for the team, not for each person.
    Equal fractional weights preserve the shared signal while preventing a
    three-person roster from being counted as three independent observations.
    """

    del engine
    count = len(team.members)
    return [1.0 / count] * count if count else []


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


def replay_and_collect(
    contests,
    data_root: str,
    problem_manifest: Mapping[str, object] | None = None,
    problem_catalog: Mapping[str, object] | None = None,
):
    """Time-ordered replay collecting everything the contract files need.

    Returns ``(contest_docs, players, engine)`` where ``contest_docs`` is the
    per-contest detail list (in chronological order) and ``players`` maps key ->
    _PlayerAcc. The engine is driven exactly like the validator: predict
    (pre-update), then process, with no look-ahead leakage.
    """
    engine = IncrementalEngine()
    problem_manifest = problem_manifest or {
        "version": "problem-types-none",
        "problems": {},
    }
    problem_catalog = problem_catalog or {
        "version": "problem-catalog-none",
        "problems": {},
    }

    contest_docs: list[dict] = []
    players: dict[str, _PlayerAcc] = {}
    problem_rating_observations: dict[str, list[dict[str, object]]] = {}

    for contest in contests:
        slug = contest_slug(contest.id)
        # 1) Predict before update -> predictedRank + concordance (no leakage).
        scores = engine.predict_scores(contest)
        pred_rank = predicted_ranks(scores)
        # Contest-level review metrics use the same effective sample as the
        # validator: participated, rostered teams only.
        conc = pairwise_concordance_for_teams(scores, contest.teams)

        # Recover team display names and the raw problem statuses (positionally
        # aligned with teams).  The loader intentionally drops statuses from
        # the rating model; the web panel derives its display-only metrics here.
        raw_contest = _raw_contest_data(data_root, contest.id)
        raw_rows = raw_contest.get("rows", []) or []
        raw_problems = raw_contest.get("problems", []) or []
        problem_overview = build_contest_problem_overview(
            contest_id=contest.id,
            raw_problems=raw_problems,
            raw_rows=raw_rows,
            manifest=problem_manifest,
            problem_catalog=(
                problem_catalog.get("problems", {})
                if isinstance(problem_catalog, Mapping)
                else {}
            ),
            contest_links=(
                raw_contest.get("contest", {}).get("refLinks", [])
                if isinstance(raw_contest.get("contest"), Mapping)
                else []
            ),
        )
        duration_minutes = contest_duration_minutes(raw_contest.get("contest", {}))
        contest_tier = classify_tier(contest)
        panel_eligible = supports_panel_metrics(raw_contest)
        observed_status_counts = [0] * len(raw_problems)
        for row in raw_rows:
            row_statuses = row.get("statuses") if isinstance(row, Mapping) else None
            if not isinstance(row_statuses, list):
                continue
            for problem_index in range(min(len(row_statuses), len(raw_problems))):
                if isinstance(row_statuses[problem_index], Mapping):
                    observed_status_counts[problem_index] += 1
        row_panel_metrics = (
            [
                extract_team_panel_metrics(
                    raw_rows[idx] if idx < len(raw_rows) else {},
                    raw_problems,
                    duration_minutes,
                )
                for idx in range(len(contest.teams))
            ]
            if panel_eligible
            else []
        )
        # Capture the team baseline before processing this contest.  The
        # seven-axis model uses this same pre-event scale and estimates only a
        # personal axis residual.
        pre_team_rating = [
            _team_pre_rating(engine, team) for team in contest.teams
        ]
        # Problem-type evidence is also derived from raw statuses.  It is kept
        # transiently on each player's accumulator and compacted into a skill
        # panel after both participation modes have been replayed.
        team_skill_evidence = []
        for idx, team in enumerate(contest.teams):
            member_weights = _team_skill_member_weights(engine, team)
            per_member = []
            for member_index, _member in enumerate(team.members):
                per_member.append(
                    _skill_problem_evidence(
                        contest_id=contest.id,
                        contest_start_at=_isoformat(contest.start_at),
                        tier=contest_tier,
                        official=bool(team.official),
                        raw_rows=raw_rows,
                        raw_row=raw_rows[idx] if idx < len(raw_rows) else {},
                        raw_problems=raw_problems,
                        manifest=problem_manifest,
                        team_pre_rating=(
                            pre_team_rating[idx] if idx < len(pre_team_rating) else None
                        ),
                        player_pre_rating=_member_mu(engine, _member.key),
                        team_rating_sd=(
                            _team_rating_sd(engine, team)
                            if idx < len(contest.teams) else None
                        ),
                        evidence_weight=(
                            member_weights[member_index]
                            if member_index < len(member_weights) else 1.0
                        ),
                        observed_status_counts=observed_status_counts,
                    )
                    if panel_eligible
                    else []
                )
            team_skill_evidence.append(per_member)

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

        # Collect leakage-free item responses against each team's pre-contest
        # rating. Explicitly missing statuses are excluded; FB is accepted.
        for problem_index, problem in enumerate(problem_overview):
            canonical = problem.get("canonicalId") or f"{contest.id}:{problem.get('alias', problem_index)}"
            for team_index, team in enumerate(contest.teams):
                if not team.official or not getattr(team, "participated", True):
                    continue
                rating = pre_team_rating[team_index]
                if rating is None or team_index >= len(raw_rows):
                    continue
                statuses = raw_rows[team_index].get("statuses") if isinstance(raw_rows[team_index], Mapping) else None
                if not isinstance(statuses, list) or problem_index >= len(statuses) or not isinstance(statuses[problem_index], Mapping):
                    continue
                outcome = statuses[problem_index].get("result")
                if outcome is None:
                    # A complete SRK status row with no result means the team
                    # did not solve this problem.  It must not vanish from the
                    # denominator, otherwise very hard problems with few
                    # attempts are systematically rated too easy.
                    observation_weight = _PROBLEM_NO_ATTEMPT_WEIGHT
                else:
                    observation_weight = 1.0
                problem_rating_observations.setdefault(str(canonical), []).append(
                    {
                        "teamRating": rating,
                        "solved": outcome in {"AC", "FB"},
                        "weight": observation_weight,
                    }
                )

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
            for member_index, member in enumerate(team.members):
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
                if idx < len(team_skill_evidence):
                    per_member = team_skill_evidence[idx]
                    if member_index < len(per_member):
                        acc.skill_evidence.extend(per_member[member_index])

                state = _display_state(engine, member.key)
                # rating_after = displayed ladder score (the 赛后分 column);
                # mu_after = internal expectation E (the chart's smooth μ line).
                rating_after = state[0] if state else None
                mu_after = state[1] if state else None
                member_perf = _perf_tail(engine, member.key)
                # Whether this contest counted toward the ladder for this member
                # (rated-contest count advanced). A gated-out row is unrated.
                rated = bool(state) and state[2] > pre_contests.get(member.key, 0)

                panel_fields = (
                    history_panel_fields(
                        tier=contest_tier,
                        solved=team.solved,
                        rank=team.rank,
                        team_count=len(contest.teams),
                        extracted=row_panel_metrics[idx],
                    )
                    if panel_eligible
                    else {}
                )

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
                        **{
                            key: _round(value) if isinstance(value, float) else value
                            for key, value in panel_fields.items()
                        },
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
                "tier": classify_tier(contest),
                "onlinePreliminary": _is_online_prelim(contest),
                "teamCount": len(contest.teams),
                "concordance": _round(conc) if conc is not None else None,
                "unrated": contest.id in UNRATED_CONTESTS,
                "unratedNote": UNRATED_CONTESTS.get(contest.id),
                "problems": problem_overview,
                "teams": team_docs,
                "_champion": champion,
            }
        )

    # Fit all problem intercepts after the replay so every contest sees the
    # same historical calibration, while team ratings remain strictly pre-event.
    problem_ratings = build_problem_rating_index(problem_rating_observations)
    for contest_doc in contest_docs:
        for problem in contest_doc.get("problems", []):
            canonical = problem.get("canonicalId") or f"{contest_doc['id']}:{problem.get('alias')}"
            record = problem_ratings.get(str(canonical))
            if record:
                problem.update({
                    "problemRating": record["problemRating"],
                    "posteriorSd": record["posteriorSd"],
                    "ratingSampleCount": record["sampleCount"],
                    "ratingEffectiveSampleCount": record.get("effectiveSampleCount", 0.0),
                    "ratingAcCount": record["acCount"],
                    "ratingWaCount": record.get("waCount", 0),
                    "ratingModel": record.get("model", "1PL"),
                    "ratingDiscrimination": record.get("discrimination", 1.0),
                    "ratingSpread": record.get("ratingSpread", 0.0),
                    "ratingSlopePosteriorSd": record.get("slopePosteriorSd"),
                    "ratingSlopeSource": record.get("slopeSource", "fixed_prior"),
                    "ratingBoundaryOutcome": bool(record.get("boundaryOutcome", False)),
                    "ratingGateReasons": list(record.get("gateReasons", [])),
                    "expectedPassRateAtReference": record["expectedPassRateAtReference"],
                })
                if record.get("problemRating") is not None:
                    key, label = difficulty_level_from_problem_rating(record["problemRating"])
                    problem["difficultyKey"] = key
                    problem["difficultyLabel"] = label
            else:
                problem.update({"problemRating": None, "difficultyKey": None, "difficultyLabel": None, "posteriorSd": None, "ratingSampleCount": 0, "ratingEffectiveSampleCount": 0.0, "ratingAcCount": 0, "ratingWaCount": 0, "ratingModel": "1PL", "ratingDiscrimination": 1.0, "ratingSpread": 0.0, "ratingSlopePosteriorSd": None, "ratingSlopeSource": "fixed_prior", "ratingBoundaryOutcome": False, "ratingGateReasons": ["no_observations"], "expectedPassRateAtReference": None})
    # The item fit is completed after the chronological replay.  Enrich the
    # already collected personal evidence with the shared item scale before
    # building panels.  This keeps team ratings leakage-free while allowing the
    # retrospective panel to explain each solve relative to calibrated problem
    # difficulty.
    for acc in players.values():
        for evidence in acc.skill_evidence:
            canonical = str(evidence.get("canonicalId") or "")
            fitted = problem_ratings.get(canonical)
            if not isinstance(fitted, Mapping):
                continue
            evidence["problemRating"] = fitted.get("problemRating")
            evidence["problemPosteriorSd"] = fitted.get("posteriorSd")
            evidence["problemModel"] = fitted.get("model", "1PL")
            evidence["problemDiscrimination"] = fitted.get("discrimination", 1.0)
    return contest_docs, players, engine


def replay_official(contests, medal_contest_ids=None):
    """Official-only replay: board, histories, team docs, and contest metrics.

    Runs the engine with ``official_only=True`` so 打星 / official:false teams are
    absent from the field entirely (no rank, no score, no influence). Produces
    everything the 正式参赛 口径 needs, all computed over the official subset:

    * ``history[key][slug]`` -- per member: this contest's recovered perf,
      post-contest display rating / internal E, rank among official teams (1224
      over the official subset), official team count, and whether it counted
      (``rated``; a gated-out row is unrated).
    * ``contest_teams[slug][team_index]`` -- per official team: ``predictedRank``
      (1224 over official strengths), ``perf``, ``preRating``, ``muDelta``, and
      ``rank`` (among official teams), plus the count of members who had rated
      official history before the contest.
    * ``contest_metrics[slug]`` -- the six pre-contest field-strength scores
      and the post-contest result weirdness. Strength admits every official
      participating team at equal weight, including wholly unknown rosters.
      Weirdness only compares teams whose three members all have history.

    ``medal_contest_ids`` is the set whose raw SRK files carry an explicit,
    positive medal rule. When omitted, direct callers retain the historical
    non-network default; the production exporter always supplies the set.

    Contests sharing the exact same ``start_at`` are all snapshotted before any
    of them updates the engine. This prevents an arbitrary ID/order tie-break
    from leaking one simultaneous result into another contest's prediction or
    strength metrics.

    Returns ``(history, contest_teams, contest_metrics, engine)``; ``engine`` is
    the terminal official engine (for the board).
    """
    engine = IncrementalEngine(official_only=True)
    history: dict[str, dict[str, dict]] = {}
    contest_teams: dict[str, dict[int, dict]] = {}
    contest_metrics: dict[str, dict] = {}

    for _, simultaneous in groupby(contests, key=lambda contest: contest.start_at):
        snapshots = []

        # Freeze every pre-contest view in this timestamp group first.
        for contest in simultaneous:
            slug = contest_slug(contest.id)
            official_idx = [
                i
                for i, team in enumerate(contest.teams)
                if engine._counts(team)  # noqa: SLF001
            ]
            counted = [contest.teams[i] for i in official_idx]
            scores = engine.predict_scores(contest)
            official_scores = [scores[i] for i in official_idx]
            pred_official = predicted_ranks(official_scores)
            official_ranks = rerank_1224(counted)

            pre_member_expect: dict[str, float] = {}
            pre_contests: dict[str, int] = {}
            known_members = []
            for team in counted:
                known = 0
                for member in team.members:
                    mu = _member_mu(engine, member.key)
                    pre_member_expect[member.key] = (
                        mu if mu is not None else PRIOR_MU
                    )
                    state = engine._players.get(member.key)  # noqa: SLF001
                    contests_before = state["contests"] if state else 0
                    pre_contests[member.key] = contests_before
                    if contests_before > 0:
                        known += 1
                known_members.append(known)

            pre_team_rating = [_team_pre_rating(engine, team) for team in counted]
            metric_teams = [
                MetricTeam(
                    rating=official_scores[j],
                    actual_rank=official_ranks[j],
                    known_members=known_members[j],
                )
                for j in range(len(counted))
            ]
            if medal_contest_ids is None:
                awards_medals = not _is_online_prelim(contest)
            else:
                awards_medals = (
                    contest.id in medal_contest_ids
                    and not _is_online_prelim(contest)
                )
            contest_metrics[slug] = compute_contest_metrics(
                metric_teams,
                awards_medals=awards_medals,
            )
            snapshots.append(
                {
                    "contest": contest,
                    "slug": slug,
                    "official_idx": official_idx,
                    "counted": counted,
                    "predicted": pred_official,
                    "ranks": official_ranks,
                    "pre_member_expect": pre_member_expect,
                    "pre_contests": pre_contests,
                    "pre_team_rating": pre_team_rating,
                    "known_members": known_members,
                }
            )

        # Preserve the established rating engine's chronological update order,
        # using only the frozen data above for public pre-contest fields.
        for snapshot in snapshots:
            contest = snapshot["contest"]
            slug = snapshot["slug"]
            official_idx = snapshot["official_idx"]
            counted = snapshot["counted"]
            pred_official = snapshot["predicted"]
            official_ranks = snapshot["ranks"]
            pre_member_expect = snapshot["pre_member_expect"]
            pre_contests = snapshot["pre_contests"]
            pre_team_rating = snapshot["pre_team_rating"]
            known_members = snapshot["known_members"]
            official_count = len(counted)

            engine.process_contest(contest)

            team_map: dict[int, dict] = {}
            for j, team in enumerate(counted):
                i = official_idx[j]
                team_perf = (
                    _perf_tail(engine, team.members[0].key)
                    if team.members
                    else None
                )
                mu_delta = _team_mu_delta(engine, team, pre_member_expect)
                pre_rating = pre_team_rating[j]
                team_map[i] = {
                    "predictedRank": pred_official[j],
                    "perf": _round(team_perf) if team_perf is not None else None,
                    "preRating": (
                        _round(pre_rating) if pre_rating is not None else None
                    ),
                    "muDelta": _round(mu_delta) if mu_delta is not None else None,
                    "rank": official_ranks[j],
                    "knownMembers": known_members[j],
                }
                for member in team.members:
                    disp = _display_state(engine, member.key)
                    if disp is None:
                        continue
                    member_perf = _perf_tail(engine, member.key)
                    state = engine._players.get(member.key)  # noqa: SLF001
                    rated = (
                        bool(state)
                        and state["contests"] > pre_contests.get(member.key, 0)
                    )
                    history.setdefault(member.key, {})[slug] = {
                        "perf": (
                            _round(member_perf)
                            if member_perf is not None
                            else None
                        ),
                        "rating_after": _round(disp[0]),
                        "mu_after": _round(disp[1]),
                        "rank": official_ranks[j],
                        "team_count": official_count,
                        "rated": rated,
                    }
            contest_teams[slug] = team_map

    return history, contest_teams, contest_metrics, engine


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


def build_archive_contest_docs(load, data_root, problem_manifest=None, problem_catalog=None):
    """Export no-roster standings as archives, outside every rating replay.

    A team's result is still useful when its members are absent from the source.
    Same-venue duplicate boards remain deduplicated and are not reintroduced.
    """
    docs = []
    for skipped in load.skipped:
        if skipped.reason != SkippedContest.REASON_NO_ROSTER:
            continue
        path = os.path.join(data_root, skipped.id + SRK_SUFFIX)
        contest = parse_contest(
            path, data_root, skipped.id.split("/")[0], 0.0, LoadResult(),
            require_roster=False,
        )
        raw = _raw_contest_data(data_root, contest.id)
        raw_rows = raw.get("rows", []) or []
        official_teams = [team for team in contest.teams if team.official]
        official_ranks = iter(rerank_1224(official_teams))
        teams = []
        for index, team in enumerate(contest.teams):
            row = raw_rows[index]
            name, org = _team_display(row)
            teams.append({
                "rank": team.rank, "name": name, "org": org,
                "solved": team.solved, "penalty": _penalty_minutes(row),
                "official": team.official, "members": [],
                "rankOfficial": next(official_ranks) if team.official else None,
                **{field: None for field in (
                    "predictedRank", "perf", "preRating", "muDelta",
                    "predictedRankOfficial", "perfOfficial", "preRatingOfficial",
                    "muDeltaOfficial", "knownMembersOfficial",
                )},
            })
        docs.append({
            "id": contest.id, "slug": contest_slug(contest.id),
            "title": contest.title, "startAt": _isoformat(contest.start_at),
            "category": contest.category, "tier": classify_tier(contest),
            "onlinePreliminary": _is_online_prelim(contest),
            "teamCount": len(teams), "teams": teams,
            "concordance": None, "contestMetrics": None,
            "archiveOnly": True, "unrated": True,
            "unratedNote": "上游榜单未提供队员名单，仅展示队伍成绩；本场不参与个人 rating 计算。",
            "_champion": _champion(teams),
            "problems": build_contest_problem_overview(
                contest_id=contest.id, raw_problems=raw.get("problems", []) or [],
                raw_rows=raw_rows, manifest=problem_manifest or {},
                problem_catalog=(problem_catalog or {}).get("problems", {}),
                contest_links=raw.get("contest", {}).get("refLinks", []),
            ),
        })
    return docs


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


def build_player_records(
    players,
    engine,
    medals=None,
    official_history=None,
    board_ranks=None,
    problem_types_version: str | None = None,
):
    """Build the full per-player detail records (terminal state + history).

    ``rating`` is ``None`` for players below the ``MIN_RATED_CONTESTS`` gate.
    Returns a dict key -> record.

    ``board_ranks`` is the optional ``{"all": {key: rank}, "official": {key: rank},
    "officialRating": {key: rating}}`` from the two finished leaderboards. When
    supplied, each record carries ``allRank`` / ``officialRank`` /
    ``officialRating`` (null when the player is absent from that board), so the
    player page renders its standings without downloading the full boards.

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
    board_ranks = board_ranks or {}
    all_rank_map = board_ranks.get("all") or {}
    official_rank_map = board_ranks.get("official") or {}
    official_rating_map = board_ranks.get("officialRating") or {}
    records: dict[str, dict] = {}
    skill_evidence: dict[str, list[dict]] = {}
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
                    "rankPercentOfficial": (
                        rank_percent(o["rank"], o["team_count"]) if o else None
                    ),
                    "ratedOfficial": o["rated"] if o else False,
                }
            )

        record = {
            "key": key,
            "name": acc.name,
            "org": acc.org,
            "contests": contests,
            "rating": rating,
            # Precomputed standings so the player page needs no leaderboard fetch.
            "allRank": all_rank_map.get(key),
            "officialRank": official_rank_map.get(key),
            "officialRating": official_rating_map.get(key),
            "history": history,
        }
        if acc.skill_evidence:
            skill_evidence[key] = list(acc.skill_evidence)
        # Per-tier medal tally (gold/silver/bronze), zero-medal tiers omitted.
        # Field is present only for players who earned at least one medal so the
        # contract stays minimal and the players-index is untouched.
        compact = _compact_medals(medals.get(key))
        if compact:
            record["medals"] = compact
        records[key] = record
    if problem_types_version:
        build_player_skill_panels(
            records,
            skill_evidence,
            taxonomy_version=problem_types_version,
        )
        compact_player_skill_panels(records)
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


def replay_schools(contests):
    """Run the school rating engine over the contests (same set as the boards).

    Voided contests (``UNRATED_CONTESTS``) are skipped so a leaked-problem board
    never moves a school's belief, matching the player boards' 口径. Returns
    ``(engine, history)`` where ``history`` maps org -> the school's per-contest
    result rows (newest first) for the 学校成绩 view.
    """
    engine = SchoolEngine()
    history: dict[str, list[dict]] = {}
    # Each school's rating after its previous contest; a school's rating only
    # moves when it competes, so this is exactly its pre-contest rating. The
    # baseline before a school's first contest is the prior reliable level.
    prior = engine.prior_rating()
    prev_rating: dict[str, float] = {}
    for contest in contests:
        if contest.id in UNRATED_CONTESTS:
            continue
        results = engine.score_contest(contest)
        if not results:
            continue
        slug = contest_slug(contest.id)
        title = contest.title
        start_at = _isoformat(contest.start_at)
        team_count = len(contest.teams)
        for result in results:
            org = result.org
            before = prev_rating.get(org, prior)
            after = engine.rating(org)
            prev_rating[org] = after
            history.setdefault(org, []).append(
                {
                    "slug": slug,
                    "title": title,
                    "startAt": start_at,
                    "teamRank": result.team_rank,
                    "teamCount": team_count,
                    "schoolRank": result.school_rank,
                    "schoolCount": result.school_count,
                    "perf": _round(result.perf),
                    "delta": _round(after - before),
                }
            )
    # Newest first, matching the player history table's order.
    for rows in history.values():
        rows.reverse()
    return engine, history


def build_schools(school_engine, min_contests=MIN_RATED_CONTESTS) -> list[dict]:
    """Build the 学校榜 rows: ``{org, rating, contests}`` ordered by rating desc.

    ``rating`` is the conservative TrueSkill-family score (``mu - k*sigma``)
    rounded to the contract precision; the engine's leaderboard already sorts by
    full-precision rating, so the order is stable.
    """
    return [
        {
            "org": standing.org,
            "rating": _round(standing.rating),
            "contests": standing.contests,
        }
        for standing in school_engine.leaderboard(min_contests=min_contests)
    ]


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


def _display_round(value: float) -> int:
    """Match JavaScript ``Math.round`` for the positive rating domain."""
    return math.floor(value + 0.5)


def build_leaderboard_assets(board, page_size=LEADERBOARD_PAGE_SIZE):
    """Build metadata, numbered pages, and per-school leaderboard slices.

    Compact row form is ``[key, name, org, rating, contests, globalRank]``. The
    rank is computed over the complete board using the same rounded-score 1224
    rule as the former browser implementation, so page and school shards never
    need the full dataset to recover a correct global rank.
    """
    if page_size <= 0:
        raise ValueError("page_size must be positive")

    ranked_rows: list[list] = []
    previous_score = None
    current_rank = 0
    for index, row in enumerate(board):
        score = _display_round(row["rating"])
        if previous_score is None or score != previous_score:
            current_rank = index + 1
        ranked_rows.append(
            [
                row["key"],
                row["name"],
                row["org"],
                row["rating"],
                row["contests"],
                current_rank,
            ]
        )
        previous_score = score

    pages = [
        ranked_rows[start : start + page_size]
        for start in range(0, len(ranked_rows), page_size)
    ]
    school_rows: dict[str, list[list]] = {}
    for row in ranked_rows:
        org = row[2].strip()
        if org:
            school_rows.setdefault(org, []).append(row)

    school_counts = sorted(
        [[org, len(rows)] for org, rows in school_rows.items()],
        key=lambda item: (-item[1], item[0]),
    )
    meta = {
        "total": len(ranked_rows),
        "pageSize": page_size,
        "pageCount": len(pages),
        "schools": school_counts,
    }
    return meta, pages, school_rows


def build_player_search_shards(records) -> dict[str, list[list]]:
    """Build compact player shards keyed by name/org prefix-character hash.

    A player is indexed under the normalized first character of both their name
    and organization. The browser derives the same two-hex md5 shard from the
    query's first character, then performs the existing substring match inside
    that much smaller candidate set.
    """
    shards: dict[str, list[list]] = {}
    for record in records.values():
        row = [
            record["key"],
            record["name"],
            record["org"],
            record["contests"],
        ]
        prefixes = {
            value.strip().lower()[:1]
            for value in (record["name"], record["org"])
            if value and value.strip()
        }
        # Multiple prefix characters can hash into the same two-hex bucket; a
        # per-record set prevents duplicate search results in that collision.
        for shard in {player_shard(prefix) for prefix in prefixes}:
            shards.setdefault(shard, []).append(row)
    for rows in shards.values():
        rows.sort(key=lambda row: (row[1].lower(), row[2].lower(), row[0]))
    return shards


def _dump_json(path: str, obj) -> int:
    """Write ``obj`` as compact UTF-8 JSON; return the byte size written."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    data = text.encode("utf-8")
    with open(path, "wb") as handle:
        handle.write(data)
    return len(data)


def _reset_dir(path: str) -> None:
    """Recreate one generated-data directory without leaving stale shards."""
    if os.path.isdir(path):
        shutil.rmtree(path)
    os.makedirs(path, exist_ok=True)


def _write_leaderboard_assets(out_dir: str, kind: str, board) -> int:
    """Write one leaderboard's metadata, pages, and school hash buckets."""
    root = os.path.join(out_dir, "leaderboards", kind)
    meta, pages, schools = build_leaderboard_assets(board)
    _dump_json(os.path.join(root, "meta.json"), meta)
    file_count = 1
    for page_number, rows in enumerate(pages, start=1):
        _dump_json(os.path.join(root, "pages", f"{page_number}.json"), rows)
        file_count += 1
    school_buckets: dict[str, dict[str, list[list]]] = {}
    for org, rows in schools.items():
        school_buckets.setdefault(player_shard(org), {})[org] = rows
    for shard, bucket in school_buckets.items():
        _dump_json(os.path.join(root, "schools", shard + ".json"), bucket)
        file_count += 1
    return file_count


def _skill_axis_metric(tier_payload, axis_index: int, axis: str):
    """Read one skill axis from either compact or verbose player payloads.

    ``write_bundle`` normally receives records after
    :func:`compact_player_skill_panels`, but accepting the verbose mapping here
    keeps this helper useful for small export fixtures and makes the boundary
    tolerant of callers that construct records themselves.
    """

    if not isinstance(tier_payload, Mapping):
        return None
    raw_axes = tier_payload.get("axes")
    if isinstance(raw_axes, Mapping):
        return raw_axes.get(axis)
    if isinstance(raw_axes, (list, tuple)) and axis_index < len(raw_axes):
        return raw_axes[axis_index]
    return None


def _skill_metric_fields(metric):
    """Return display/rank fields from either compact or verbose metrics."""

    if isinstance(metric, Mapping):
        return (
            metric.get("score"),
            metric.get("topPercent"),
            metric.get("grade"),
            metric.get("coverage", 0.0),
            metric.get("uniqueProblems", 0),
            metric.get("rankScore", metric.get("score")),
            metric.get("effectiveProblems", metric.get("uniqueProblems", 0)),
            metric.get("evidenceLevel", "established"),
            metric.get("confidence", 1.0),
        )
    if isinstance(metric, (list, tuple)):
        # PlayerSkillAxisRaw: score, mastery, topPercent, grade, coverage,
        # uniqueProblems, successWeight, exposureWeight, validContests.  v2+
        # appends rankScore/effectiveProblems/evidenceLevel/confidence; use the
        # calibrated rank score for ordering instead of the display score.
        values = list(metric) + [None] * 6
        if len(metric) >= 15:
            return (
                values[0], values[2], values[3], values[4], values[5],
                values[9], values[11], values[13], values[12],
            )
        return (
            values[0], values[2], values[3], values[4], values[5],
            values[0], values[5], "legacy", 1.0,
        )
    return None, None, None, 0.0, 0, None, 0.0, "missing", 0.0


def _skill_metric_values(tier_payload):
    """Iterate axis metrics from compact lists or verbose axis mappings."""

    if not isinstance(tier_payload, Mapping):
        return ()
    axes = tier_payload.get("axes")
    if isinstance(axes, Mapping):
        return axes.values()
    if isinstance(axes, (list, tuple)):
        return axes
    return ()


def build_skill_leaderboard_index(records: Mapping[str, Mapping[str, object]]) -> dict:
    """Build the standalone seven-axis skill leaderboard index.

    Rows use a fixed tuple order in ``rowFields`` to keep the public JSON much
    smaller than repeating nine property names for every player.  Legacy
    compact metrics retain their historical coverage gate; calibrated metrics
    carry their own uncertainty fields and are ranked even for small samples.
    Ranks are competition ranks (ties share a rank) sorted by descending
    calibrated lower-bound score and then the stable player key.
    """

    modes = ("all", "official")
    has_v2_metrics = any(
        (
            isinstance(metric, (list, tuple)) and len(metric) >= 15
        )
        or (
            isinstance(metric, Mapping)
            and ("rankScore" in metric or "effectiveProblems" in metric)
        )
        for record in records.values()
        for mode_payload in (record.get("skillPanel", {}) or {}).values()
        if isinstance(mode_payload, Mapping)
        for tier_payload in mode_payload.values()
        if isinstance(tier_payload, Mapping)
        for metric in _skill_metric_values(tier_payload)
        if isinstance(metric, (list, tuple, Mapping))
    )
    tiers = ("overall",)
    boards: dict[str, dict[str, dict[str, list[list[object]]]]] = {
        mode: {
            tier: {axis: [] for axis in PROBLEM_TYPE_AXES}
            for tier in tiers
        }
        for mode in modes
    }

    for mode in modes:
        for tier in tiers:
            for axis_index, axis in enumerate(PROBLEM_TYPE_AXES):
                candidates: list[tuple[str, str, str, float, float, object, int, float]] = []
                for key, record in records.items():
                    panel = record.get("skillPanel") if isinstance(record, Mapping) else None
                    mode_payload = panel.get(mode) if isinstance(panel, Mapping) else None
                    tier_payload = mode_payload.get(tier) if isinstance(mode_payload, Mapping) else None
                    metric = _skill_axis_metric(tier_payload, axis_index, axis)
                    score, top_percent, grade, coverage, unique_problems, rank_score, effective_problems, evidence_level, confidence = _skill_metric_fields(metric)
                    try:
                        score_value = float(score)
                        top_value = float(top_percent)
                        coverage_value = float(coverage)
                        unique_value = int(unique_problems)
                        rank_value = float(rank_score)
                        effective_value = float(effective_problems)
                        confidence_value = float(confidence)
                    except (TypeError, ValueError):
                        continue
                    if not all(math.isfinite(value) for value in (score_value, top_value, coverage_value, rank_value, effective_value, confidence_value)):
                        continue
                    # Legacy compact fixtures retain the old gate for backwards
                    # compatibility; current calibrated exports rank every
                    # axis with evidence, including small samples.
                    is_legacy_metric = not (
                        (
                            isinstance(metric, (list, tuple))
                            and len(metric) >= 15
                        )
                        or (
                            isinstance(metric, Mapping)
                            and (
                                "rankScore" in metric
                                or "effectiveProblems" in metric
                            )
                        )
                    )
                    if is_legacy_metric and (
                        coverage_value < SKILL_MIN_COVERAGE
                        or unique_value < SKILL_MIN_UNIQUE_PROBLEMS
                    ):
                        continue
                    candidates.append(
                        (
                            str(key),
                            str(record.get("name", "")),
                            str(record.get("org", "")),
                            score_value,
                            top_value,
                            grade,
                            unique_value,
                            coverage_value,
                            rank_value,
                            effective_value,
                            evidence_level,
                            confidence_value,
                        )
                    )

                candidates.sort(key=lambda item: (-item[8], item[0]))
                rows: list[list[object]] = []
                previous_score: float | None = None
                previous_rank = 0
                for position, candidate in enumerate(candidates, start=1):
                    if previous_score is None or candidate[8] != previous_score:
                        previous_rank = position
                        previous_score = candidate[8]
                    key, name, org, score, top_percent, grade, unique, coverage, rank_score, effective, evidence, confidence = candidate
                    base_row = [previous_rank, key, name, org, score, top_percent, grade, unique, coverage]
                    rows.append(base_row if not has_v2_metrics else base_row + [rank_score, effective, evidence, confidence])
                boards[mode][tier][axis] = rows

    return {
        "version": SKILL_LEADERBOARD_INDEX_VERSION if has_v2_metrics else "skill-leaderboards-v1",
        "modes": list(modes),
        "tiers": list(tiers),
        "axes": list(PROBLEM_TYPE_AXES),
        "sample": {
            "minCoverage": SKILL_MIN_COVERAGE,
            "minUniqueProblems": SKILL_MIN_UNIQUE_PROBLEMS,
        },
        "rowFields": list(SKILL_LEADERBOARD_ROW_FIELDS) if has_v2_metrics else [
            "rank", "key", "name", "org", "score", "topPercent", "grade",
            "uniqueProblems", "coverage",
        ],
        "boards": boards,
    }


def _write_skill_leaderboard_assets(out_dir: str, records) -> int:
    """Write one compact axis board per mode/tier.

    Player shards are intentionally not used for this view: the browser can
    request exactly the selected axis (usually a few KB) instead of fetching
    all 256 player shards and sorting tens of thousands of rows on the main
    thread.
    """
    root = os.path.join(out_dir, "skill-leaderboards")
    # ``write_bundle`` creates the compact combined ``index.json`` before
    # calling this helper.  Keep it alongside the per-axis files; resetting the
    # directory here would erase that public contract.
    os.makedirs(root, exist_ok=True)
    file_count = 0
    for mode in ("all", "official"):
        for tier in ("overall",):
            for axis in PROBLEM_TYPE_AXES:
                rows = []
                for record in records.values():
                    tier_data = (
                        record.get("skillPanel", {})
                        .get(mode, {})
                        .get(tier)
                    )
                    if not isinstance(tier_data, Mapping):
                        continue
                    metrics = tier_data.get("axes")
                    if not isinstance(metrics, list):
                        continue
                    axis_index = PROBLEM_TYPE_AXES.index(axis)
                    if axis_index >= len(metrics) or not isinstance(metrics[axis_index], list):
                        continue
                    metric = metrics[axis_index]
                    score = metric[0] if len(metric) > 0 else None
                    rank_score = metric[9] if len(metric) > 9 else score
                    if not isinstance(score, (int, float)) or not isinstance(rank_score, (int, float)):
                        continue
                    rows.append({
                        "key": record["key"],
                        "name": record["name"],
                        "org": record["org"],
                        "score": score,
                        "topPercent": metric[2] if len(metric) > 2 else None,
                        "grade": metric[3] if len(metric) > 3 else None,
                        "uniqueProblems": metric[5] if len(metric) > 5 else 0,
                        "coverage": metric[4] if len(metric) > 4 else 0.0,
                        "rankScore": rank_score,
                        "effectiveProblems": metric[11] if len(metric) > 11 else metric[5] if len(metric) > 5 else 0,
                        "evidenceLevel": metric[13] if len(metric) > 13 else "legacy",
                        "confidence": metric[12] if len(metric) > 12 else 1.0,
                    })
                rows.sort(key=lambda row: (-row["rankScore"], row["key"]))
                # One axis board is the heaviest page payload (a full leaderboard
                # for the caliber).  Repeating the twelve field names on every
                # row cost ~59% of the file, so publish the same
                # ``rowFields`` + array-row layout the combined index uses; the
                # frontend expands it back into row objects.
                _dump_json(
                    os.path.join(root, mode, tier, axis + ".json"),
                    {
                        "version": "skill-panel-v4",
                        "mode": mode,
                        "tier": tier,
                        "axis": axis,
                        "rowFields": list(SKILL_LEADERBOARD_AXIS_FIELDS),
                        "rows": [
                            [row[field] for field in SKILL_LEADERBOARD_AXIS_FIELDS]
                            for row in rows
                        ],
                    },
                )
                file_count += 1
    return file_count


def build_problems_index(contest_docs) -> list[dict]:
    """Flatten contest problem metadata into one filter-friendly index.

    Contest detail documents keep problems nested so the detail page can be
    fetched independently.  The index is intentionally a small, stable row
    shape for pages that need to filter across contests, years, types and
    difficulty without downloading every contest document.
    """
    rows: list[dict] = []
    for contest in contest_docs or ():
        if not isinstance(contest, Mapping):
            continue
        problems = contest.get("problems")
        if not isinstance(problems, list):
            continue
        for problem in problems:
            if not isinstance(problem, Mapping):
                continue
            type_keys = problem.get("typeKeys")
            type_labels = problem.get("typeLabels")
            rows.append(
                {
                    "contestSlug": str(contest.get("slug") or ""),
                    "contestTitle": contest.get("title") or "",
                    "startAt": contest.get("startAt") or "",
                    "category": contest.get("category") or "",
                    "tier": contest.get("tier") or "provincial",
                    "alias": str(problem.get("alias") or ""),
                    "title": problem.get("title") or None,
                    "canonicalId": problem.get("canonicalId") or None,
                    "typeKeys": list(type_keys) if isinstance(type_keys, list) else [],
                    "typeLabels": list(type_labels) if isinstance(type_labels, list) else [],
                    "detailTags": list(problem.get("detailTags"))
                    if isinstance(problem.get("detailTags"), list)
                    else [],
                    "problemUrl": problem.get("problemUrl") or None,
                    "status": problem.get("status") or "unknown",
                    "confidence": problem.get("confidence", 0.0),
                    "solveRate": problem.get("solveRate"),
                    "problemRating": problem.get("problemRating"),
                    **(
                        {
                            "difficultyKey": problem.get("difficultyKey"),
                            "difficultyLabel": problem.get("difficultyLabel"),
                        }
                        if problem.get("difficultyKey") is not None
                        else {}
                    ),
                    "accepted": problem.get("accepted"),
                    "submitted": problem.get("submitted"),
                    "eligibleTeams": problem.get("eligibleTeams", 0),
                }
            )
    return rows


def write_bundle(
    out_dir,
    contest_docs,
    records,
    engine,
    official_board=None,
    main_board=None,
    schools=None,
    school_history=None,
    predictions=None,
    problem_manifest=None,
    data_source=None,
):
    """Write the entire contract bundle under ``out_dir``. Returns file count.

    Leaderboards are written as metadata + 100-row pages + school hash buckets.
    Player search is independently prefix-sharded, so neither feature downloads
    the former multi-megabyte global indexes. ``main_board`` is the
    all-participation board (rebuilt from ``engine`` when omitted);
    ``official_board`` is the official-only board.
    """
    os.makedirs(out_dir, exist_ok=True)
    file_count = 0

    # meta.json
    rated_players = sum(
        1 for r in records.values() if len(r["history"]) >= MIN_RATED_CONTESTS
    )
    predictions = predictions or []
    meta = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "engine": ENGINE,
        "counts": {
            "contests": len(contest_docs),
            "archiveContests": sum(bool(doc.get("archiveOnly")) for doc in contest_docs),
            "players": len(records),
            "ratedPlayers": rated_players,
            "predictions": len(predictions),
        },
    }
    if isinstance(problem_manifest, Mapping):
        meta["skillTaxonomyVersion"] = problem_manifest.get("version")
        meta["skillScoreModel"] = SKILL_SCORE_MODEL
        meta["skillScoreScale"] = "rating"
        meta["skillSourceWindow"] = problem_manifest.get("sourceWindow")
        meta["skillProblemCount"] = len(problem_manifest.get("problems", {}))
        meta["skillAxes"] = problem_manifest.get("axes", [])
    if isinstance(data_source, Mapping):
        meta["dataSource"] = dict(data_source)
    _dump_json(os.path.join(out_dir, "meta.json"), meta)
    file_count += 1

    if isinstance(problem_manifest, Mapping):
        _dump_json(
            os.path.join(out_dir, "problem-types", "2023-present.json"),
            published_problem_manifest(problem_manifest),
        )
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
                "tier": doc["tier"],
                "onlinePreliminary": doc["onlinePreliminary"],
                "teamCount": doc["teamCount"],
                "champion": doc["_champion"],
                "unrated": doc.get("unrated", False),
                "archiveOnly": doc.get("archiveOnly", False),
                "contestMetrics": doc.get("contestMetrics"),
            }
        )
        detail = {k: v for k, v in doc.items() if k != "_champion"}
        _dump_json(
            os.path.join(out_dir, "contests", doc["slug"] + ".json"), detail
        )
        file_count += 1
    _dump_json(os.path.join(out_dir, "contests-index.json"), index)
    file_count += 1

    # problems-index.json (flat problem rows for cross-contest filtering)
    _dump_json(
        os.path.join(out_dir, "problems-index.json"),
        build_problems_index(contest_docs),
    )
    file_count += 1

    # search/players/<prefix-hash>.json. Reset generated shards first so a data
    # shrink cannot leave stale candidates from an older export.
    search_root = os.path.join(out_dir, "search", "players")
    _reset_dir(search_root)
    for shard, rows in build_player_search_shards(records).items():
        _dump_json(os.path.join(search_root, shard + ".json"), rows)
        file_count += 1

    # Delete superseded monolithic indexes when exporting over an older bundle.
    for legacy_name in (
        "players-index.json",
        "leaderboard.json",
        "leaderboard_official.json",
    ):
        legacy_path = os.path.join(out_dir, legacy_name)
        if os.path.isfile(legacy_path):
            os.remove(legacy_path)

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

    # Paged leaderboards. Reset the root to avoid stale high-numbered pages or
    # schools when the source dataset shrinks between deployments.
    _reset_dir(os.path.join(out_dir, "leaderboards"))
    if main_board is None:
        main_board = build_leaderboard(engine)
    file_count += _write_leaderboard_assets(out_dir, "all", main_board)

    if official_board is not None:
        file_count += _write_leaderboard_assets(
            out_dir, "official", official_board
        )

    # Independent problem-type axis boards.  This must be emitted after player
    # records are compacted so the wire format stays exactly in sync with the
    # player detail decoder.
    file_count += _write_skill_leaderboard_assets(out_dir, records)
    # Keep a complete manifest for diagnostics and future server-side paging;
    # the UI requests the smaller per-axis files above.
    _dump_json(
        os.path.join(out_dir, "skill-leaderboards", "index.json"),
        build_skill_leaderboard_index(records),
    )
    file_count += 1

    # schools.json (学校榜: Bayesian reliable-level school ranking)
    if schools is not None:
        _dump_json(os.path.join(out_dir, "schools.json"), schools)
        file_count += 1

    # school-history/<shard>.json (per-school 学校成绩 rows, sharded by md5(org))
    if school_history is not None:
        shards: dict[str, dict] = {}
        for org, rows in school_history.items():
            shards.setdefault(player_shard(org), {})[org] = rows
        for shard, bucket in shards.items():
            _dump_json(
                os.path.join(out_dir, "school-history", shard + ".json"), bucket
            )
            file_count += 1

    # Upcoming-contest predictions. Reset generated details so removing a
    # roster specification cannot leave a stale public page behind.
    prediction_root = os.path.join(out_dir, "predictions")
    _reset_dir(prediction_root)
    prediction_index = []
    for document in predictions:
        prediction_index.append(prediction_index_entry(document))
        _dump_json(
            os.path.join(prediction_root, document["slug"] + ".json"),
            document,
        )
        file_count += 1
    _dump_json(os.path.join(out_dir, "predictions-index.json"), prediction_index)
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
        "--problem-types",
        default=DEFAULT_PROBLEM_TYPES,
        help="curated problem-type manifest (default: 2023-present QOJ registry); pass an empty value to disable",
    )
    parser.add_argument(
        "--problem-catalog",
        default=DEFAULT_PROBLEM_CATALOG,
        help="problem title/link catalog (default: data/problem-catalog.json); pass an empty value to disable",
    )
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

    problem_manifest = _load_problem_type_manifest(args.problem_types)
    print(
        f"Problem-type manifest: {problem_manifest.get('version')} / "
        f"{len(problem_manifest.get('problems', {}))} classified entries.",
        flush=True,
    )

    problem_catalog = _load_problem_catalog(args.problem_catalog)
    print(
        f"Problem catalog: {problem_catalog.get('version')} / "
        f"{len(problem_catalog.get('problems', {}))} title/link entries.",
        flush=True,
    )

    contest_docs, players, engine = replay_and_collect(
        load.contests,
        args.data,
        problem_manifest=problem_manifest,
        problem_catalog=problem_catalog,
    )

    # Tiered gold/silver/bronze medals, re-derived read-only from the raw srk
    # standings. Reuse the existing LoadResult so medals share the pipeline's
    # scan, dedup, and coverage decisions instead of re-loading from disk.
    medals = collect_medals(args.data, min_coverage=args.min_coverage, load_result=load)
    medal_contest_ids = collect_medal_contest_ids(args.data, load.contests)
    medalists = sum(1 for tally in medals.values() if _compact_medals(tally))
    print(f"Collected medals for {medalists} medalists.", flush=True)
    print(
        f"Explicit medal data: {len(medal_contest_ids)} contest(s).",
        flush=True,
    )

    # Second board: replay again counting only official participation (打星 /
    # official:false teams treated as absent -- no field, no rank, no score). The
    # same replay collects each player's per-contest official perf/rating and the
    # per-contest official team docs, so the player and contest pages can render
    # the official-only 口径.
    (
        official_history,
        official_contest_teams,
        official_contest_metrics,
        engine_official,
    ) = replay_official(load.contests, medal_contest_ids=medal_contest_ids)
    official_board = build_leaderboard(engine_official)
    main_board = build_leaderboard(engine)
    print(f"Official-only board: {len(official_board)} rated players.", flush=True)

    prediction_medal_cache = {}

    def prediction_medal_history(included_contest_ids):
        if included_contest_ids not in prediction_medal_cache:
            prediction_medal_cache[included_contest_ids] = collect_medals(
                args.data,
                min_coverage=args.min_coverage,
                load_result=load,
                included_contest_ids=included_contest_ids,
            )
        return prediction_medal_cache[included_contest_ids]

    prediction_docs = build_predictions(
        PREDICTION_SPECS,
        load.contests,
        medals=medals,
        medal_history_provider=prediction_medal_history,
    )
    print(f"Upcoming predictions: {len(prediction_docs)} contest(s).", flush=True)

    # Precompute each player's standings on both boards so the player page renders
    # its rank/rating without downloading the (multi-MB) leaderboards.
    board_ranks = {
        "all": {row["key"]: i + 1 for i, row in enumerate(main_board)},
        "official": {row["key"]: i + 1 for i, row in enumerate(official_board)},
        "officialRating": {row["key"]: row["rating"] for row in official_board},
    }

    # 学校榜: Bayesian reliable-level school rating over the same contest set,
    # plus each school's per-contest results for the 学校成绩 view.
    school_engine, school_history = replay_schools(load.contests)
    schools = build_schools(school_engine)
    print(f"School board: {len(schools)} rated schools.", flush=True)

    # Merge the official-only per-team fields into each contest doc's teams, so the
    # contest page's 仅正式 view can render official ranks / predictions / perf. A
    # 打星 team has no official entry -> its *Official fields stay null.
    for doc in contest_docs:
        off_teams = official_contest_teams.get(doc["slug"], {})
        doc["contestMetrics"] = official_contest_metrics.get(doc["slug"])
        for i, team in enumerate(doc["teams"]):
            o = off_teams.get(i)
            team["predictedRankOfficial"] = o["predictedRank"] if o else None
            team["perfOfficial"] = o["perf"] if o else None
            team["preRatingOfficial"] = o["preRating"] if o else None
            team["muDeltaOfficial"] = o["muDelta"] if o else None
            team["rankOfficial"] = o["rank"] if o else None
            team["knownMembersOfficial"] = o["knownMembers"] if o else None

    archive_docs = build_archive_contest_docs(load, args.data, problem_manifest, problem_catalog)
    contest_docs.extend(archive_docs)
    contest_docs.sort(key=lambda doc: (doc["startAt"], doc["id"]))
    print(f"Browsable archives: {len(archive_docs)} no-roster contests; {len(contest_docs)} total contests.", flush=True)

    records = build_player_records(
        players,
        engine,
        medals=medals,
        official_history=official_history,
        board_ranks=board_ranks,
        problem_types_version=problem_manifest.get("version"),
    )
    file_count = write_bundle(
        args.out,
        contest_docs,
        records,
        engine,
        official_board=official_board,
        main_board=main_board,
        schools=schools,
        school_history=school_history,
        predictions=prediction_docs,
        problem_manifest=problem_manifest,
        data_source={
            "repository": "https://github.com/algoux/srk-collection.git",
            "commit": _git_head(args.data),
            "sourceBoards": len(load.contests) + len(load.skipped),
            "scoringContests": len(load.contests),
            "archiveContests": len(archive_docs),
            "deduplicatedBoards": sum(
                1 for item in load.skipped if getattr(item, "reason", "") == "duplicate-of"
            ),
        },
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
