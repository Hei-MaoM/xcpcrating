"""Tiered gold / silver / bronze medal accounting from raw srk standings.

Read-only and additive: this module does not touch any scoring rule, the loader's
dedup logic, or :mod:`xcpc_rating.tier`'s classification. It re-reads the original
``*.srk.json`` files, reproduces the medal allocation srk renders, and buckets
every medal by the contest's prestige tier
(:func:`xcpc_rating.tier.classify_tier`).

The medal rule lives in each file's ``series``
----------------------------------------------
Every srk standings file carries a ``series`` array. The medal series is the one
whose ``segments`` carry ``style`` values ``gold`` / ``silver`` / ``bronze``.
Each segment's size is read **per segment** (not as a cumulative cutoff) and
accumulated into cumulative rank endpoints. Two ``rule`` option forms appear:

* ``options.count.value = [g, s, b]`` -- per-segment team counts, accumulated to
  cumulative cutoffs ``[g, g + s, g + s + b]``: gold = positions 1..g, silver =
  the next s, bronze = the next b, over the eligible standings in rank order.
* ``options.ratio.value = [r1, r2, r3]`` -- per-segment fractions. Each segment's
  size is ``ri * denominator`` under the configured rounding
  (``floor`` / ``ceil`` / ``round``, default ``ceil``), accumulated with
  ``Decimal`` to avoid float drift. ``denominator`` is the count of eligible
  teams that *scored* (solved >= 1) when ``ratio.denominator == "scored"``,
  otherwise the full eligible-team count.

``noTied: true`` cuts strictly at the computed position; by default a band is
extended to include every team tied (same solved + penalty) with the team at the
cutoff, so tied teams never split across two colors.

Eligibility (official teams, optional marker filter)
----------------------------------------------------
Medals are allocated only over **official** teams (``user.official`` not False);
a starred / unofficial team is removed from the pool entirely, so an official team
above it moves up into the slot. Some boards carry ``options.filter.byMarker``:
only official teams whose ``user.markers`` list contains that marker id are
eligible (e.g. a final awards medals only to 本科 teams). Teams without the
marker drop out of the pool exactly like a starred team.

ICPC-preset default fallback (zero / missing count)
---------------------------------------------------
An ICPC-preset medal series whose ``count.value`` is absent or ``[0, 0, 0]`` (and
has no ``ratio``) falls back to the ICPC default bands, per segment:
gold = ``ceil(0.1 * n)``, silver = ``2 * gold``, bronze = ``3 * gold``, where
``n`` is the eligible (official + optional marker) pool size. A non-ICPC preset
with a ``[0, 0, 0]`` count (or a ratio rounding to 0) awards nothing.

Public surface
--------------
* :func:`parse_medal_rule` -- one file's per-segment ``[gold, silver, bronze]``
  counts, or ``None`` if it has no medal series.
* :func:`allocate_medals` -- ``{member_key: 'gold'|'silver'|'bronze'}`` for one
  parsed srk dict (coaches dropped, in-contest key dedup).
* :func:`collect_medals` -- scan the in-scope boards (scored boards plus
  duplicate-of provincial copies) and aggregate per member per prestige tier.

Everything here is a pure function over data already on disk; nothing mutates
shared state.
"""

from __future__ import annotations

import json
import math
import os
from collections import defaultdict
from decimal import Decimal
from typing import Optional

from .identity import clean_org, is_coach, player_key, resolve_i18n
from .loader import SRK_SUFFIX, load_contests
from .model import Contest
from .tier import (
    TIER_FINAL,
    TIER_INVITATIONAL,
    TIER_PROVINCIAL,
    TIER_REGIONAL,
    classify_tier,
)

# Medal colors, ordered best-to-worst. The list order is load-bearing: it maps a
# cumulative-cutoff index (0/1/2) onto a color and drives the per-tier tally shape.
MEDAL_GOLD = "gold"
MEDAL_SILVER = "silver"
MEDAL_BRONZE = "bronze"
MEDAL_COLORS = (MEDAL_GOLD, MEDAL_SILVER, MEDAL_BRONZE)

# All prestige tiers, used to seed an empty per-tier tally so every player record
# has a uniform shape regardless of where they medaled.
ALL_TIERS = (TIER_FINAL, TIER_REGIONAL, TIER_INVITATIONAL, TIER_PROVINCIAL)

# srk ratio denominator that counts only teams that scored at least one problem.
_DENOMINATOR_SCORED = "scored"

# The ICPC preset's default medal split: cumulative 10% / 20% / 30% bands. Used
# as the fallback cutoffs when an ICPC-preset medal series ships no usable count.
_ICPC_PRESET = "icpc"
_ICPC_DEFAULT_RATIOS = (0.1, 0.2, 0.3)


def _js_round(value: float) -> int:
    """Round half up (0.5 -> 1), matching the JS/official-utils ``round``."""
    return int(math.floor(value + 0.5))


def _rounding_fn(name):
    """Resolve a rounding name to a function. Default ``ceil`` (srk spec default).

    Mirrors ``standard_ranklist_utils.ranklist._rounding_fn``: ``floor`` /
    ``round`` (half-up) / ``ceil`` (the documented ratio default).
    """
    if name == "floor":
        return math.floor
    if name == "round":
        return _js_round
    return math.ceil


def _icpc_default_segments(eligible_total: int) -> list:
    """ICPC-preset fallback per-segment counts ``[gold, 2*gold, 3*gold]``.

    Fallback for a medal series that ships a zero / missing ``count`` (and no
    ``ratio``): 金 = ⌈10% × 正式参赛队数⌉, 银 = 2×金, 铜 = 3×金 (per-segment counts;
    ``eligible_total`` is the official + optional marker pool, the same field srk
    renders standings over). The downstream accumulation turns this into
    cumulative endpoints ``[g, 3g, 6g]``.
    """
    gold = int(math.ceil(0.1 * eligible_total))
    return [gold, 2 * gold, 3 * gold]


# --------------------------------------------------------------------------- #
# Medal-series discovery and rule parsing
# --------------------------------------------------------------------------- #


def _find_medal_series(srk_dict: dict) -> Optional[dict]:
    """Return the series whose segments carry gold/silver/bronze styles, or None.

    A board's medal series is identified purely by its segment ``style`` values
    (not its title), so a renamed title ("Gold Medalist" vs "金奖") never matters.
    The first matching series wins; non-medal series (rank-only ``R#``, org-unique
    ``S#``) are ignored.
    """
    for series in srk_dict.get("series") or []:
        if not isinstance(series, dict):
            continue
        styles = {
            (seg.get("style") or "").lower()
            for seg in (series.get("segments") or [])
            if isinstance(seg, dict)
        }
        if styles & set(MEDAL_COLORS):
            return series
    return None


def _accumulate(segments) -> list:
    """Turn per-segment counts ``[g, s, b]`` into cumulative endpoints ``[g, g+s, g+s+b]``.

    The srk medal rule's ``value`` array is **per-segment** (``[4,4,4]`` = 4 gold,
    4 silver, 4 bronze -- see standard-ranklist docs), so the cumulative rank
    endpoint for each color is the running sum. Padded to three entries.
    """
    endpoints = []
    acc = 0
    for v in list(segments)[:3]:
        acc += v
        endpoints.append(acc)
    while len(endpoints) < 3:
        endpoints.append(endpoints[-1] if endpoints else 0)
    return endpoints


def _cumulative_cutoffs(
    srk_dict: dict,
    eligible_total: int,
    scored_total: int,
    submitted_total: Optional[int] = None,
):
    """Resolve a medal series to cumulative rank endpoints ``[c1, c2, c3]``.

    Returns ``(endpoints, no_tied)`` or ``None`` when the board has no medal
    series. Faithful to the official ``standard-ranklist-utils`` ICPC rule: the
    medal ``value`` array is **per-segment** (counts per color, not cumulative),
    so endpoints are the running sum -- gold up to ``c1``, silver up to ``c2``,
    bronze up to ``c3``.

    * ``ratio.value`` -- per-segment ratios accumulated, then each cumulative
      ratio is scaled by the denominator and rounded. ``denominator`` is
      ``all`` (official pool, default) / ``submitted`` / ``scored``; ``rounding``
      is ``floor`` / ``round`` / ``ceil`` (default ``ceil``).
    * ``count.value`` -- per-segment counts accumulated. An ICPC-preset all-zero
      count falls back to the default segments.
    * no count/ratio under an ICPC preset -- default segments
      (:func:`_icpc_default_segments`); any other preset awards nothing.
    """
    series = _find_medal_series(srk_dict)
    if series is None:
        return None

    rule = series.get("rule") or {}
    options = rule.get("options") or {}
    is_icpc_preset = str(rule.get("preset") or "").lower() == _ICPC_PRESET

    count = options.get("count") or {}
    ratio = options.get("ratio") or {}

    # noTied may live on either the count or ratio options object.
    no_tied = bool(count.get("noTied") or ratio.get("noTied"))

    if "ratio" in options and isinstance(ratio.get("value"), (list, tuple)):
        denom_kind = ratio.get("denominator", "all")
        if denom_kind == _DENOMINATOR_SCORED:
            denom = scored_total
        elif denom_kind == "submitted":
            denom = submitted_total if submitted_total is not None else eligible_total
        else:
            denom = eligible_total
        rounder = _rounding_fn(ratio.get("rounding", "ceil"))
        # Accumulate as Decimal (matching the official utils) so 0.1 + 0.2 is
        # exactly 0.3, not 0.30000000000000004 -- otherwise ceil(0.3*20) would
        # wrongly round 6.0000000001 up to 7.
        acc = Decimal(0)
        endpoints = []
        for r in list(ratio["value"])[:3]:
            acc += Decimal(str(r))
            endpoints.append(int(rounder(float(acc * denom))))
        while len(endpoints) < 3:
            endpoints.append(endpoints[-1] if endpoints else 0)
        return endpoints, no_tied

    if "count" in options and isinstance(count.get("value"), (list, tuple)):
        values = [int(v) for v in list(count["value"])[:3]]
        # An ICPC-preset all-zero count is a placeholder for the default bands,
        # not a deliberate "award nothing".
        if is_icpc_preset and sum(values) == 0:
            values = _icpc_default_segments(eligible_total)
        return _accumulate(values), no_tied

    # No usable count or ratio. Under the ICPC preset use the default segments;
    # under any other preset award nothing.
    if is_icpc_preset:
        return _accumulate(_icpc_default_segments(eligible_total)), no_tied
    return [0, 0, 0], no_tied


def parse_medal_rule(srk_dict: dict) -> Optional[list]:
    """Return one board's ``[gold, silver, bronze]`` *counts*, or ``None``.

    ``None`` means the file has no medal series at all. Otherwise the three
    de-cumulated per-color counts are returned (gold = ``c1``, silver = ``c2 -
    c1``, bronze = ``c3 - c2``). An ICPC-preset series shipping a zero / missing
    count resolves to the preset's default 10/20/30 bands (see
    :func:`_cumulative_cutoffs`); a non-ICPC placeholder yields ``[0, 0, 0]``.

    Note: ``ratio``-based boards need the live standings to size the denominator,
    so this counts-only helper resolves a ratio against the file's own rows
    (eligible / scored totals) to stay self-contained. :func:`allocate_medals`
    performs the authoritative allocation directly over the standings.
    """
    if _find_medal_series(srk_dict) is None:
        return None

    eligible_rows = _eligible_rows(srk_dict)
    eligible_total = len(eligible_rows)
    scored_total = sum(1 for row in eligible_rows if _row_scored(row))
    submitted_total = sum(1 for row in eligible_rows if _row_submitted(row))

    resolved = _cumulative_cutoffs(srk_dict, eligible_total, scored_total, submitted_total)
    if resolved is None:
        return None
    cutoffs, _no_tied = resolved
    c1, c2, c3 = cutoffs
    gold = max(c1, 0)
    silver = max(c2 - c1, 0)
    bronze = max(c3 - c2, 0)
    return [gold, silver, bronze]


# --------------------------------------------------------------------------- #
# Eligible-pool construction (official + optional marker filter)
# --------------------------------------------------------------------------- #


def _marker_filter(srk_dict: dict) -> Optional[str]:
    """Return the ``filter.byMarker`` marker id for the medal series, or None."""
    series = _find_medal_series(srk_dict)
    if series is None:
        return None
    options = (series.get("rule") or {}).get("options") or {}
    flt = options.get("filter") or {}
    marker = flt.get("byMarker")
    return str(marker) if marker else None


def _row_markers(row: dict) -> set:
    """Marker ids carried by a standings row (``user.markers`` plus ``marker``)."""
    user = row.get("user", {}) or {}
    markers = set()
    raw_list = user.get("markers")
    if isinstance(raw_list, (list, tuple)):
        markers.update(str(m) for m in raw_list)
    single = user.get("marker")
    if single:
        markers.add(str(single))
    return markers


def _row_official(row: dict) -> bool:
    """Whether a row is an official (ranked) team. Defaults True when absent."""
    user = row.get("user", {}) or {}
    return bool(user.get("official", True))


def _row_scored(row: dict) -> bool:
    """Whether a row solved at least one problem (for ratio ``scored`` denom)."""
    score = row.get("score", {}) or {}
    value = score.get("value")
    try:
        return int(value) >= 1
    except (TypeError, ValueError):
        return False


def _row_submitted(row: dict) -> bool:
    """Whether a row made at least one submission (for ratio ``submitted`` denom).

    A submission shows up as a problem status carrying a non-null ``result``
    (matching the official utils' ``submitted`` denominator test). Falls back to
    ``_row_scored`` when a board ships no per-problem statuses.
    """
    statuses = row.get("statuses")
    if isinstance(statuses, (list, tuple)) and statuses:
        return any(
            isinstance(s, dict) and s.get("result") is not None for s in statuses
        )
    return _row_scored(row)


def _eligible_rows(srk_dict: dict) -> list:
    """The medal-eligible standings rows, in standings order.

    A row is eligible iff it is official **and** (when the board carries a
    ``filter.byMarker``) it carries that marker. Starred / non-marker teams are
    dropped entirely, so they neither hold a slot nor receive a medal -- exactly
    srk's rendering. Order is preserved (rows are already in rank order).
    """
    rows = srk_dict.get("rows") or []
    marker = _marker_filter(srk_dict)
    eligible = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if not _row_official(row):
            continue
        if marker is not None and marker not in _row_markers(row):
            continue
        eligible.append(row)
    return eligible


# --------------------------------------------------------------------------- #
# Tie-aware color cutoffs
# --------------------------------------------------------------------------- #


def _score_key(row: dict) -> tuple:
    """The ``(solved, penalty)`` ordering key used to detect tied teams."""
    score = row.get("score", {}) or {}
    value = score.get("value")
    try:
        solved = int(value)
    except (TypeError, ValueError):
        solved = 0
    time = score.get("time")
    if isinstance(time, (list, tuple)):
        penalty = time[0] if time else 0
    else:
        penalty = time
    try:
        penalty = float(penalty)
    except (TypeError, ValueError):
        penalty = 0.0
    return solved, penalty


def _extend_for_ties(eligible: list, cutoff: int, no_tied: bool) -> int:
    """Adjust a cumulative cutoff to not split a tie group, unless ``no_tied``.

    With ``no_tied`` we cut strictly at ``cutoff`` teams. Otherwise, if the team
    at position ``cutoff`` is tied (same solved + penalty) with the team just
    after it, the band extends forward to include every tied team -- so two teams
    on the same score never land in different medal colors. Returns the adjusted
    team count (clamped to the eligible pool size).
    """
    n = len(eligible)
    cutoff = max(0, min(cutoff, n))
    if no_tied or cutoff == 0 or cutoff >= n:
        return cutoff
    boundary_key = _score_key(eligible[cutoff - 1])
    extended = cutoff
    while extended < n and _score_key(eligible[extended]) == boundary_key:
        extended += 1
    return extended


# --------------------------------------------------------------------------- #
# Member expansion (shared identity rules)
# --------------------------------------------------------------------------- #


def _team_member_keys(row: dict, seen: set, dedup_warnings: list) -> list:
    """Expand a row's competitors to identity keys (coaches dropped, deduped).

    Reuses the loader's exact rules: coaches/advisors are removed, an empty name
    is skipped, and a key already seen earlier in this contest is dropped (first
    occurrence wins) so a player counted on one team is not double-counted on
    another row of the same board. ``seen`` is the running per-contest key set.
    """
    user = row.get("user", {}) or {}
    org_field = user.get("organization")
    keys = []
    for raw in user.get("teamMembers") or []:
        if not isinstance(raw, dict):
            continue
        if is_coach(raw):
            continue
        name_field = raw.get("name")
        if not resolve_i18n(name_field):
            continue
        key = player_key(name_field, org_field)
        if key in seen:
            dedup_warnings.append(key)
            continue
        seen.add(key)
        keys.append(key)
    return keys


# --------------------------------------------------------------------------- #
# Per-board allocation
# --------------------------------------------------------------------------- #


def allocate_medals(srk_dict: dict) -> dict:
    """Allocate medals for one parsed srk dict.

    Returns ``{member_key: 'gold'|'silver'|'bronze'}``. The eligible pool (official
    teams, optionally marker-filtered) is walked in rank order; cumulative cutoffs
    (count or ratio, tie-extended unless ``noTied``) partition it into the three
    colors. Every competitor on a medaling team gets that team's color, with
    coaches removed and in-contest identity dedup applied. A board with no medal
    series or all-zero counts returns ``{}``.
    """
    eligible = _eligible_rows(srk_dict)
    eligible_total = len(eligible)
    scored_total = sum(1 for row in eligible if _row_scored(row))
    submitted_total = sum(1 for row in eligible if _row_submitted(row))

    resolved = _cumulative_cutoffs(srk_dict, eligible_total, scored_total, submitted_total)
    if resolved is None:
        return {}
    cutoffs, no_tied = resolved

    # Tie-extend each cumulative cutoff, then enforce monotonicity so the bands
    # never overlap (a later color cannot start before an earlier one ended).
    adjusted = []
    running = 0
    for cutoff in cutoffs:
        extended = _extend_for_ties(eligible, cutoff, no_tied)
        extended = max(extended, running)
        adjusted.append(extended)
        running = extended
    c1, c2, c3 = adjusted

    # Map each eligible row index -> medal color via the cumulative bands.
    medals: dict[str, str] = {}
    seen_keys: set = set()
    dedup_warnings: list = []
    for idx, row in enumerate(eligible):
        if idx < c1:
            color = MEDAL_GOLD
        elif idx < c2:
            color = MEDAL_SILVER
        elif idx < c3:
            color = MEDAL_BRONZE
        else:
            break  # past the bronze cutoff: no further medals
        for key in _team_member_keys(row, seen_keys, dedup_warnings):
            medals[key] = color
    return medals


# --------------------------------------------------------------------------- #
# Corpus-wide collection
# --------------------------------------------------------------------------- #


def _empty_tally() -> dict:
    """A fresh per-tier {tier: {gold, silver, bronze}} tally, all zeros."""
    return {tier: {color: 0 for color in MEDAL_COLORS} for tier in ALL_TIERS}


def _load_srk(data_root: str, contest_id: str) -> dict:
    """Re-read one contest's raw srk.json (same recovery path as export_web)."""
    path = os.path.join(data_root, contest_id + SRK_SUFFIX)
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _classify_id(contest_id: str, srk_dict: dict, category: str) -> str:
    """Classify a board's prestige tier without mutating tier.py.

    Builds a throwaway :class:`Contest` shell (id/title/category only; tier
    classification reads no other field) and defers to
    :func:`xcpc_rating.tier.classify_tier`.
    """
    title = resolve_i18n((srk_dict.get("contest") or {}).get("title")) or contest_id
    shell = Contest(
        id=contest_id,
        title=title,
        start_at=None,
        category=category,
        teams=(),
    )
    return classify_tier(shell)


def _category_of(contest_id: str) -> str:
    """Top-level category from a contest id's leading path segment."""
    return contest_id.split("/", 1)[0]


def collect_medals(
    data_root: str,
    min_coverage: float = 0.70,
    load_result=None,
) -> dict:
    """Scan the in-scope boards and aggregate medals per member per tier.

    The scan set is the 161 boards the rating pipeline actually consumes:

    * every **scored** contest (``LoadResult.contests``) -- bucketed by its own
      prestige tier (a co-branded "X邀请赛暨Y省赛" classifies as invitational and
      awards its medals over the full field), and
    * every **duplicate-of** provincial copy that dedup dropped
      (``LoadResult.skipped`` entries whose ``reason`` starts with
      ``"duplicate-of:"``), with one critical distinction between a co-branded
      省赛/邀请赛 board and a literal duplicate:

      - a copy that is a **literal duplicate** of its scored source (same
        standings size) is the SAME contest filed twice under both ``ccpc/`` and
        ``provincial/`` -- it is **skipped** so its medals are not double-counted
        (they were already awarded on the scored board);
      - a copy that is a genuine **province-internal subset** (fewer rows than
        its source -- e.g. ``fjcpc12th`` 112 福建 teams vs the 285-team source)
        is the 省赛 sub-ranking, so its medals are awarded in the **provincial**
        tier (distinct from the source's invitational medals over the full field).

    Boards skipped for **low coverage** are excluded (they never enter scoring).

    Returns ``{member_key: {tier: {gold, silver, bronze}}}`` with a uniform
    all-tier shape per member. ``load_result`` may be passed to reuse an existing
    :class:`~xcpc_rating.loader.LoadResult` (avoids a second disk scan).
    """
    if load_result is None:
        load_result = load_contests(data_root, min_coverage=min_coverage)

    tally: dict[str, dict] = defaultdict(_empty_tally)

    # Scored boards -- each in its own classified tier.
    for contest in load_result.contests:
        srk_dict = _load_srk(data_root, contest.id)
        tier = _classify_id(contest.id, srk_dict, contest.category)
        for member_key, color in allocate_medals(srk_dict).items():
            tally[member_key][tier][color] += 1

    # Duplicate-of provincial copies of co-branded events.
    for skipped in load_result.skipped:
        reason = str(skipped.reason)
        if not reason.startswith("duplicate-of:"):
            continue
        source_id = reason.split("duplicate-of:", 1)[1].strip()
        dup_srk = _load_srk(data_root, skipped.id)
        try:
            source_srk = _load_srk(data_root, source_id)
            source_rows = len(source_srk.get("rows") or [])
        except OSError:
            source_rows = -1  # source missing: treat the copy as a real subset
        dup_rows = len(dup_srk.get("rows") or [])
        # Literal duplicate of the (already-counted) scored board -> skip.
        if dup_rows == source_rows:
            continue
        # Genuine province-internal subset -> provincial-tier medals.
        for member_key, color in allocate_medals(dup_srk).items():
            tally[member_key][TIER_PROVINCIAL][color] += 1

    # Demote the defaultdict to a plain dict for a clean, picklable return.
    return {key: value for key, value in tally.items()}


# --------------------------------------------------------------------------- #
# Empirical self-check (run as a module, never imported for side effects)
# --------------------------------------------------------------------------- #


def _empirical_report(data_root: str) -> None:
    """Print a hand-verifiable summary over the live corpus (manual QA only)."""
    load_result = load_contests(data_root)
    scored = load_result.contests
    duplicates = [
        s for s in load_result.skipped if str(s.reason).startswith("duplicate-of:")
    ]
    target_ids = [c.id for c in scored] + [s.id for s in duplicates]
    print(f"Target boards scanned: {len(target_ids)} "
          f"({len(scored)} scored + {len(duplicates)} duplicate-of)")

    with_rule = 0
    zero_only = []
    for cid in target_ids:
        srk = _load_srk(data_root, cid)
        rule = parse_medal_rule(srk)
        if rule is None:
            print(f"  NO medal series: {cid}")
        else:
            with_rule += 1
            if sum(rule) == 0:
                zero_only.append(cid)
    print(f"Boards with a medal series: {with_rule}")
    print(f"Boards whose rule awards zero medals: {len(zero_only)}")

    tally = collect_medals(data_root, load_result=load_result)
    totals = {color: 0 for color in MEDAL_COLORS}
    for per_tier in tally.values():
        for tier_counts in per_tier.values():
            for color in MEDAL_COLORS:
                totals[color] += tier_counts[color]
    grand = sum(totals.values())
    print(f"Total medals awarded: {grand} "
          f"(gold={totals['gold']} silver={totals['silver']} bronze={totals['bronze']})")
    print(f"Distinct medalists: {len(tally)}")


if __name__ == "__main__":  # pragma: no cover - manual QA entry point
    import sys

    root = sys.argv[1] if len(sys.argv) > 1 else "/tmp/srk-collection/official"
    _empirical_report(root)
