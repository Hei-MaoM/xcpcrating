"""Scan and parse srk.json standings files into Contest objects.

The loader walks ``{root}/{icpc,ccpc,provincial}/**/*.srk.json``, parses each
file into a :class:`~xcpc_rating.model.Contest`, applies coach removal and
identity normalization, computes standard competition ranks ("1224" style),
and filters out contests whose member-list coverage falls below a threshold.
"""

import json
import os
from datetime import datetime

from .identity import clean_org, display_name, is_coach, player_key, resolve_i18n
from .model import Contest, Member, Team

CATEGORIES = ("icpc", "ccpc", "provincial")
# Admission rule (v6): a board is admitted as long as it carries at least one row
# with a valid roster; coverage is no longer a hard gate. ``min_coverage``
# defaults open (0.0) so a single rostered row is enough, and only an *additional*
# explicitly-supplied threshold can still reject low-coverage boards. A board with
# no rostered row at all is dropped (reason "no-roster"); no-roster rows on an
# admitted board remain ghosts (the pre-existing behaviour, unchanged here).
DEFAULT_MIN_COVERAGE = 0.0
SRK_SUFFIX = ".srk.json"

# Same-venue dual-board dedup tuning.
# Two boards are candidates if their start dates differ by at most this many
# days, and they are judged the same physical contest when their member-key
# overlap (over the smaller board) reaches this fraction.
DEDUP_MAX_DAY_GAP = 1
DEDUP_MIN_OVERLAP = 0.5
# Category priority used to break ties when two same-venue boards have an
# identical team count. Lower index wins (is kept).
DEDUP_CATEGORY_PRIORITY = ("icpc", "ccpc", "provincial")

# Online preliminaries (网络预选赛 / 网络选拔赛 / "... Online Contest") are
# nationwide qualifiers that share a large fraction of their roster with every
# onsite contest held around the same date, so the member-overlap heuristic would
# wrongly collapse a real onsite board into the (much larger) online board. They
# are never a dual board of anything, so they are excluded from the same-venue
# dedup entirely. Matched case-insensitively against the title.
DEDUP_PRELIM_TITLE_MARKERS = (
    "网络预选", "网络选拔", "online contest", "online qualification",
)


class SkippedContest:
    """A contest that did not make it into the final set.

    id:       contest id (relative path without the ``.srk.json`` suffix).
    coverage: member-list coverage at parse time (0.0..1.0).
    reason:   why it was skipped. ``"no-roster"`` when the board carries no
              rostered row at all (coverage 0.0); ``"low-coverage"`` when an
              explicitly-supplied ``min_coverage`` threshold still rejects a
              partially-rostered board; or ``"duplicate-of: <kept-id>"`` for
              same-venue dual-board dedup.

    Backward compatibility: this object is also an indexable 2-tuple-like view
    ``(id, coverage)`` so existing callers that unpack ``(cid, cov)`` or read
    ``skipped[i][1]`` keep working unchanged.
    """

    REASON_LOW_COVERAGE = "low-coverage"
    REASON_NO_ROSTER = "no-roster"

    def __init__(self, contest_id: str, coverage: float, reason: str):
        self.id = contest_id
        self.coverage = coverage
        self.reason = reason

    def __getitem__(self, index):
        return (self.id, self.coverage)[index]

    def __iter__(self):
        return iter((self.id, self.coverage))

    def __len__(self):
        return 2

    def __eq__(self, other):
        if isinstance(other, SkippedContest):
            return (self.id, self.coverage, self.reason) == (
                other.id, other.coverage, other.reason,
            )
        if isinstance(other, (tuple, list)):
            return tuple(other) == (self.id, self.coverage)
        return NotImplemented

    def __hash__(self):
        # Hash over the (id, coverage) tuple view, consistent with __eq__'s
        # tuple-equality path so the object is usable in sets/dicts. (Two
        # instances differing only by reason hash-collide but remain unequal,
        # which is permitted.)
        return hash((self.id, self.coverage))

    def __repr__(self):
        return (f"SkippedContest(id={self.id!r}, coverage={self.coverage!r}, "
                f"reason={self.reason!r})")


class LoadResult:
    """Outcome of a load run.

    contests: list[Contest] that passed the coverage gate (and same-venue
              dedup), sorted by (start_at, id).
    skipped:  list[SkippedContest]; each behaves like a ``(contest_id,
              coverage)`` tuple for backward compatibility and additionally
              carries a ``reason`` string.
    warnings: list[str] of non-fatal issues (parse errors, duplicate keys).
    """

    def __init__(self):
        self.contests = []
        self.skipped = []
        self.warnings = []


def _to_number(value, default=0):
    """Coerce a possibly-missing numeric value to a number."""
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return value
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_penalty(score: dict) -> float:
    """Extract the numeric penalty from a row score.

    ``score.time`` may be ``[value, unit]`` (take value), a bare number, or
    missing (treated as 0).
    """
    time = score.get("time")
    if isinstance(time, (list, tuple)):
        return _to_number(time[0] if time else None, 0)
    return _to_number(time, 0)


def _parse_solved(score: dict) -> int:
    """Extract solved count from ``score.value`` (int)."""
    return int(_to_number(score.get("value"), 0))


def _row_submission_count(row: dict) -> int:
    """Total submissions a standings row made (the participation gate).

    The srk per-problem detail lives in ``row.statuses`` -- a list whose entries
    carry an integer ``tries`` and/or a ``solutions`` array (one entry per
    submission). We sum ``tries`` where present and otherwise fall back to the
    length of ``solutions`` for that problem, then add any top-level
    ``row.solutions`` array (an alternate flat form some boards use). A row with
    no detail at all sums to 0; callers must still treat a ``solved > 0`` row as
    a participant (a solve implies at least one submission even when the board
    omits the detail).
    """
    total = 0
    statuses = row.get("statuses")
    if isinstance(statuses, list):
        for status in statuses:
            if not isinstance(status, dict):
                continue
            tries = status.get("tries")
            if isinstance(tries, (int, float)):
                total += int(tries)
            else:
                solutions = status.get("solutions")
                if isinstance(solutions, list):
                    total += len(solutions)
    solutions = row.get("solutions")
    if isinstance(solutions, list):
        total += len(solutions)
    return total


def _parse_participated(row: dict, solved: int) -> bool:
    """Whether a row is a scoring participant (made >= 1 submission).

    ``True`` when the row made at least one submission, or solved at least one
    problem (a solve necessarily implies a submission, covering boards that omit
    the per-problem detail). ``False`` only for a true 0-submission, 0-solve row
    -- a registered-but-absent team that is displayed but never scored.
    """
    if solved > 0:
        return True
    return _row_submission_count(row) > 0


def _parse_start_at(contest_meta: dict) -> datetime:
    """Parse ``contest.startAt`` (ISO 8601, possibly with timezone)."""
    raw = contest_meta.get("startAt")
    if not raw:
        raise ValueError("missing contest.startAt")
    # datetime.fromisoformat handles offsets like +08:00 on modern Python.
    return datetime.fromisoformat(raw)


def _parse_members(user: dict, warnings: list, contest_id: str, seen: set):
    """Resolve a row's members into a Member tuple.

    Coaches are dropped. A key already seen earlier in this contest is
    dropped from the current team (first occurrence wins) and a warning is
    recorded.
    """
    members = []
    for raw in user.get("teamMembers") or []:
        if not isinstance(raw, dict):
            continue
        if is_coach(raw):
            continue
        name_field = raw.get("name")
        if not resolve_i18n(name_field):
            continue
        org_field = user.get("organization")
        key = player_key(name_field, org_field)
        if key in seen:
            warnings.append(
                f"{contest_id}: duplicate player key dropped: {key}"
            )
            continue
        seen.add(key)
        members.append(
            Member(
                key=key,
                display_name=display_name(name_field),
                org=clean_org(org_field),
            )
        )
    return tuple(members)


def _assign_ranks(rows: list):
    """Assign standard competition ranks ("1224") over parsed rows.

    rows: list of dicts with ``solved`` and ``penalty``. Already in standings
    order. Adjacent rows with an identical ``(solved, penalty)`` share the
    earliest 1-based position.
    """
    ranks = []
    prev_key = None
    for idx, row in enumerate(rows):
        key = (row["solved"], row["penalty"])
        if idx == 0 or key != prev_key:
            current_rank = idx + 1
        ranks.append(current_rank)
        prev_key = key
    return ranks


def parse_contest(path: str, root: str, category: str,
                  min_coverage: float, result: LoadResult):
    """Parse one srk.json file. Returns a Contest or None (skipped)."""
    rel = os.path.relpath(path, root)
    contest_id = rel[: -len(SRK_SUFFIX)] if rel.endswith(SRK_SUFFIX) else rel
    contest_id = contest_id.replace(os.sep, "/")

    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)

    contest_meta = data.get("contest", {})
    start_at = _parse_start_at(contest_meta)
    title = resolve_i18n(contest_meta.get("title")) or contest_id

    raw_rows = data.get("rows", [])
    seen_keys = set()
    parsed = []
    rows_with_members = 0

    for row in raw_rows:
        user = row.get("user", {}) or {}
        score = row.get("score", {}) or {}
        members = _parse_members(user, result.warnings, contest_id, seen_keys)
        if members:
            rows_with_members += 1
        official = user.get("official", True)
        solved = _parse_solved(score)
        parsed.append(
            {
                "solved": solved,
                "penalty": _parse_penalty(score),
                "members": members,
                "official": bool(official),
                "participated": _parse_participated(row, solved),
            }
        )

    total = len(parsed)
    coverage = (rows_with_members / total) if total else 0.0
    # Admission rule (v6): admit any board with >= 1 rostered row. A board with
    # no rostered row at all is dropped as "no-roster"; the explicitly-supplied
    # ``min_coverage`` (default 0.0) can additionally reject a partially-rostered
    # board, recorded as "low-coverage" to keep the two causes distinguishable.
    if rows_with_members < 1:
        result.skipped.append(
            SkippedContest(contest_id, coverage,
                           SkippedContest.REASON_NO_ROSTER)
        )
        return None
    if coverage < min_coverage:
        result.skipped.append(
            SkippedContest(contest_id, coverage,
                           SkippedContest.REASON_LOW_COVERAGE)
        )
        return None

    ranks = _assign_ranks(parsed)
    teams = tuple(
        Team(
            rank=ranks[idx],
            solved=row["solved"],
            penalty=row["penalty"],
            members=row["members"],
            official=row["official"],
            participated=row["participated"],
        )
        for idx, row in enumerate(parsed)
    )

    return Contest(
        id=contest_id,
        title=title,
        start_at=start_at,
        category=category,
        teams=teams,
    )


def _iter_files(root: str):
    """Yield (path, category) for every srk.json under the wanted categories."""
    for category in CATEGORIES:
        base = os.path.join(root, category)
        if not os.path.isdir(base):
            continue
        for dirpath, _dirs, files in os.walk(base):
            for name in files:
                if name.endswith(SRK_SUFFIX):
                    yield os.path.join(dirpath, name), category


def _member_keys(contest: Contest) -> set:
    """Collect the set of member keys appearing anywhere in a contest."""
    keys = set()
    for team in contest.teams:
        for member in team.members:
            keys.add(member.key)
    return keys


def _is_same_venue(keys_a: set, keys_b: set) -> bool:
    """Decide whether two boards represent the same physical contest.

    Overlap is measured over the smaller member set so a strict subset board
    (the provincial slice of a larger invitational) still counts as the same
    venue. Empty boards never match (no signal to compare).
    """
    smaller = min(len(keys_a), len(keys_b))
    if smaller == 0:
        return False
    overlap = len(keys_a & keys_b) / smaller
    return overlap >= DEDUP_MIN_OVERLAP


def _is_online_prelim(contest: Contest) -> bool:
    """True for a nationwide online preliminary (excluded from venue dedup)."""
    title = (contest.title or "").lower()
    return any(marker in title for marker in DEDUP_PRELIM_TITLE_MARKERS)


def _keep_winner(a: Contest, b: Contest) -> tuple:
    """Pick which of two same-venue boards to keep.

    Rule: more teams wins; on a tie, the higher-priority category (icpc >
    ccpc > provincial) wins. Returns ``(keep, drop)``.
    """
    if len(a.teams) != len(b.teams):
        return (a, b) if len(a.teams) > len(b.teams) else (b, a)

    def priority(contest: Contest) -> int:
        try:
            return DEDUP_CATEGORY_PRIORITY.index(contest.category)
        except ValueError:
            return len(DEDUP_CATEGORY_PRIORITY)

    return (a, b) if priority(a) <= priority(b) else (b, a)


def _group_same_venue(contests: list) -> list:
    """Cluster same-venue boards via union-find over candidate pairs.

    Candidates are pairs whose start dates differ by at most
    ``DEDUP_MAX_DAY_GAP`` days; a pair is unioned when its member overlap
    reaches the threshold. Transitivity (A==B, B==C => one group) follows from
    union-find. Returns a list of index groups (each a list of indices into
    ``contests``).
    """
    n = len(contests)
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x: int, y: int) -> None:
        parent[find(x)] = find(y)

    keys = [_member_keys(c) for c in contests]
    dates = [c.start_at.date() for c in contests]
    prelim = [_is_online_prelim(c) for c in contests]

    for i in range(n):
        if prelim[i]:
            continue
        for j in range(i + 1, n):
            if prelim[j]:
                continue
            if abs((dates[i] - dates[j]).days) > DEDUP_MAX_DAY_GAP:
                continue
            if _is_same_venue(keys[i], keys[j]):
                union(i, j)

    groups = {}
    for idx in range(n):
        groups.setdefault(find(idx), []).append(idx)
    return [g for g in groups.values() if len(g) > 1]


def _dedup_same_venue(result: LoadResult) -> None:
    """Drop same-venue dual-board duplicates in place.

    For each cluster of same-venue boards, keep a single winner (most teams,
    then category priority) and record every dropped board in ``skipped`` with
    a ``"duplicate-of: <kept-id>"`` reason.
    """
    contests = result.contests
    groups = _group_same_venue(contests)
    if not groups:
        return

    drop_indices = set()
    for group in groups:
        winner = contests[group[0]]
        for idx in group[1:]:
            winner, _ = _keep_winner(winner, contests[idx])
        winner_id = winner.id
        for idx in group:
            contest = contests[idx]
            if contest is winner:
                continue
            drop_indices.add(idx)
            result.skipped.append(
                SkippedContest(contest.id, 1.0,
                               f"duplicate-of: {winner_id}")
            )

    result.contests = [
        c for idx, c in enumerate(contests) if idx not in drop_indices
    ]


def load_contests(root: str, min_coverage: float = DEFAULT_MIN_COVERAGE,
                  dedup: bool = True) -> LoadResult:
    """Load all eligible contests under ``root``.

    Returns a :class:`LoadResult` whose ``contests`` are sorted by
    ``(start_at, id)``. Files that fail to parse are recorded as warnings and
    skipped. Admission rule (v6): a board is admitted as long as it carries at
    least one rostered row; a board with no rostered row at all is recorded in
    ``skipped`` with reason ``"no-roster"``. ``min_coverage`` defaults open
    (0.0); an explicitly-supplied positive threshold can still reject a
    partially-rostered board (recorded with reason ``"low-coverage"``).

    When ``dedup`` is True (default), a same-venue dual-board dedup pass runs
    after parsing: physical contests that appear twice (e.g. an invitational
    board and its provincial slice on the same day) are collapsed to one, and
    the dropped boards are recorded in ``skipped`` with a ``"duplicate-of:
    <kept-id>"`` reason.
    """
    result = LoadResult()
    for path, category in _iter_files(root):
        try:
            contest = parse_contest(path, root, category, min_coverage, result)
        except (json.JSONDecodeError, ValueError, KeyError, OSError) as exc:
            rel = os.path.relpath(path, root)
            result.warnings.append(f"{rel}: parse failed: {exc}")
            continue
        if contest is not None:
            result.contests.append(contest)

    if dedup:
        _dedup_same_venue(result)

    result.contests.sort(key=lambda c: (c.start_at, c.id))
    return result
