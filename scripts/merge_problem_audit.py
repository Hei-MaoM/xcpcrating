#!/usr/bin/env python3
"""Merge independently audited problem metadata into the public data bundle.

The builders deliberately write reviewable candidate files instead of editing
the production catalog.  This script is the single, deterministic merge point:
it joins the candidates with the raw SRK inventory and the older evidence maps,
rejects collection/rank/tutorial URLs, writes the seven-axis manifest and
catalog, and materialises one JSON document per contest under
``data/problem/<year>/<contest>.json``.

It is intentionally conservative about provenance.  A contest-level page may
be retained as ``sourceUrl``/evidence, but it is never emitted as
``problemUrl``.  Rows that still lack a trustworthy title, link, or algorithm
classification remain explicitly unresolved for the two independent review
passes instead of being silently fabricated.
"""

from __future__ import annotations

import csv
import json
import math
import re
import shutil
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.parse import unquote, urlparse


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from xcpc_rating.problem_tags import DETAIL_TAG_LABELS, normalize_detail_tags  # noqa: E402
from xcpc_rating.problem_types import PROBLEM_TYPE_AXES, PROBLEM_TYPE_LABELS, normalize_label_weights  # noqa: E402


TARGET_YEARS = (2026, 2025, 2024, 2023, 2022)
INDEX_PATH = ROOT / "web" / "public" / "data" / "problems-index.json"
RAW_ROOT = ROOT / "vendor" / "srk-collection" / "official"
MANIFEST_PATH = ROOT / "data" / "problem-types" / "2023-present-all-qoj-v2.json"
CATALOG_PATH = ROOT / "data" / "problem-catalog.json"
OUT_ROOT = ROOT / "data" / "problem"
AUDIT_ROOT = ROOT / "work" / "problem-audit"
TARGET_CONTESTS_PATH = AUDIT_ROOT / "target-contests-full.tsv"
RESEARCH_ROOT = ROOT / "work" / "qoj-research"
QOJ_INDEX_PATH = AUDIT_ROOT / "qoj-problem-index-2022-2026.json"
QOJ_EXPANDED_INDEX_PATH = AUDIT_ROOT / "qoj-problem-index-expanded.json"
QOJ_ASSIGNMENTS_PATH = AUDIT_ROOT / "qoj-assignments-final.json"
EXTERNAL_CANDIDATES_PATH = AUDIT_ROOT / "external-problem-candidates.json"
MANUAL_OVERRIDES_PATH = AUDIT_ROOT / "manual-problem-overrides.json"

# A few source inventories expose the same problem set under more than one
# contest slug.  For these combined events the Codeforces Gym dashboard is the
# clearest contest identity, while the QOJ tag is shared by both slugs.  Give
# the explicit Gym record precedence so a shared QOJ id cannot be interpreted
# as a cross-contest mismatch by downstream reviewers.
CF_IDENTITY_OVERRIDES = {
    "icpc/icpc2023/icpc2023jinan": "104901",
    "provincial/gd/gdcpc23rd": "106550",
    "provincial/js/jscpc11th": "106550",
}


def read_json(path: Path, default: Any) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=False)
        handle.write("\n")
    temporary.replace(path)


def clean_text(value: Any) -> str | None:
    if isinstance(value, Mapping):
        value = (
            value.get("zh-CN")
            or value.get("zh_cn")
            or value.get("en")
            or value.get("fallback")
        )
    if not isinstance(value, str):
        return None
    value = " ".join(value.replace("\u00a0", " ").split()).strip()
    return value or None


def valid_title(value: Any) -> str | None:
    value = clean_text(value)
    if not value:
        return None
    # Contest labels occasionally land in the title column when a mirror
    # returns a category header instead of a statement row.  They are not
    # useful problem names and must not survive into the public index.
    if value == "502 Bad Gateway" or value.lower() in {
        "bad gateway",
        "unknown",
        "null",
        "ccpc",
        "icpc",
        "problem",
        "题目",
        "未命名题目",
    }:
        return None
    # SRK sometimes stores the six-character colour swatch in the title slot.
    if len(value) == 6 and re.fullmatch(r"[0-9a-fA-F]{6}", value):
        return None
    # Replacement characters indicate a broken source encoding.  Keep a
    # legitimate title containing one only when no better source exists; the
    # merge report will still expose it for review.
    if "\ufffd" in value:
        return None
    return value


def clean_external_title(value: Any) -> str | None:
    """Normalise titles copied from online judge dashboards.

    Codeforces Gym mirrors occasionally append the input/output format to the
    title cell.  Keeping that boilerplate makes title comparisons noisy and
    can make an otherwise correct row look like a different problem.
    """

    title = valid_title(value)
    if not title:
        return None
    title = re.sub(r"\s+standard input/output\b.*$", "", title, flags=re.IGNORECASE)
    return valid_title(title)


_BAD_URL_PARTS = (
    "/rank",
    "/standings",
    "/ranking",
    "/download",
    "/tutorial",
    "/attachment",
    ".pdf",
)


def individual_url(value: Any) -> str | None:
    """Return *value* only when it identifies one problem statement."""

    if not isinstance(value, str) or not value.strip():
        return None
    value = value.strip()
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    path = unquote(parsed.path.rstrip("/")).lower()
    if any(token in path for token in _BAD_URL_PARTS):
        return None
    parts = [part for part in path.split("/") if part]
    host = parsed.netloc.lower().split(":", 1)[0]

    if host.endswith("codeforces.com"):
        if re.search(r"/gym/\d+/problem/[a-z0-9][a-z0-9_-]*$", path):
            return value
        if re.search(r"/contest/\d+/problem/[a-z0-9][a-z0-9_-]*$", path):
            return value
        return None
    if host.endswith("qoj.ac") or host.endswith("ucup.ac"):
        if re.search(r"/problem/\d+$", path):
            return value
        if re.search(r"/contest/\d+/problem/\d+$", path):
            return value
        return None
    if host.endswith("nowcoder.com"):
        if re.search(r"/acm/contest/\d+/[a-z0-9][a-z0-9_-]*$", path):
            return value
        if re.search(r"/acm/problem/[a-z0-9][a-z0-9_-]*$", path):
            return value
        return None
    if host.endswith("luogu.com.cn") and re.search(r"/problem/p\d+$", path):
        return value
    if host.endswith("vjudge.net") and ("/problem/" in path or "/problemset/" in path):
        return value
    if host.endswith("pintia.cn"):
        if "/problem-sets/" in path and "/problems/" in path:
            return value
        return None
    if host.endswith("atuer.cn"):
        # Atuer/Hydro exposes a problem as ``/p/<problem-id>``.  The route
        # does not contain the word ``problem`` and therefore needs an
        # explicit platform rule; the contest query parameter is retained so
        # a reused provincial problem still points at the selected event.
        if re.fullmatch(r"/p/[a-z0-9][a-z0-9_-]*", path):
            return value
        return None
    if "problem" in parts and len(parts) >= 2:
        return value
    # A few official mirrors put the problem alias in the final path component
    # but always include an explicit problem-ish noun in the preceding path.
    if len(parts) >= 2 and any(token in parts[-2] for token in ("problem", "question", "task")):
        return value
    return None


def canonical_problem_url(value: Any) -> str | None:
    """Return a validated direct problem URL with the preferred QOJ host.

    Jiangly mirrors expose the same numeric QOJ problem ids.  Keeping the
    public link on QOJ makes the source policy deterministic and prevents a
    higher-priority mirror report from hiding an exact QOJ record.
    """

    direct = individual_url(value)
    if not direct:
        return None
    parsed = urlparse(direct)
    host = parsed.netloc.lower().split(":", 1)[0]
    path = unquote(parsed.path.rstrip("/")).lower()
    if host.endswith("jiang.ly"):
        match = re.fullmatch(r"/problem/(\d+)", path)
        if match:
            return f"https://qoj.ac/problem/{match.group(1)}"
    return direct


def title_from_nested(value: Any) -> str | None:
    if isinstance(value, Mapping):
        for key in ("title", "name", "problemTitle"):
            result = valid_title(value.get(key))
            if result:
                return result
    return valid_title(value)


def key_for(contest_key: str, alias: str) -> str:
    return f"{contest_key}:{alias}"


def contest_slug(contest_key: str) -> str:
    return contest_key.replace("/", "__")


def alias_sort(alias: str) -> tuple[int, str]:
    match = re.fullmatch(r"([A-Z])(\d*)", alias.upper())
    if not match:
        return (999, alias)
    return (ord(match.group(1)) - 65, match.group(2))


def walk_records(value: Any) -> Iterable[tuple[str | None, Mapping[str, Any]]]:
    """Yield (explicit key, record) pairs from the various research shapes."""

    if isinstance(value, Mapping):
        # A direct key -> record map.
        for key, record in value.items():
            if key in {"labels", "items", "unresolved", "problems", "version", "axes"}:
                continue
            if isinstance(record, Mapping):
                yield str(key), record
        for container_key in ("labels", "items", "problems"):
            nested = value.get(container_key)
            if isinstance(nested, Mapping):
                for key, record in nested.items():
                    if isinstance(record, Mapping):
                        yield str(key), record
            elif isinstance(nested, list):
                for record in nested:
                    if isinstance(record, Mapping):
                        explicit = record.get("problemKey") or record.get("key")
                        yield (str(explicit) if explicit else None), record
    elif isinstance(value, list):
        for record in value:
            if isinstance(record, Mapping):
                explicit = record.get("problemKey") or record.get("key")
                yield (str(explicit) if explicit else None), record


def extract_labels(record: Mapping[str, Any]) -> dict[str, float]:
    raw = record.get("labels")
    if not isinstance(raw, Mapping):
        return {}
    try:
        normalized = normalize_label_weights(raw)
    except (TypeError, ValueError):
        normalized = {}
    if len(normalized) > 2:
        normalized = dict(sorted(normalized.items(), key=lambda item: (-item[1], item[0]))[:2])
        total = sum(normalized.values())
        normalized = {key: value / total for key, value in normalized.items()}
    return normalized


def parse_label_string(value: Any) -> dict[str, float]:
    if isinstance(value, Mapping):
        return extract_labels({"labels": value})
    if not isinstance(value, str):
        return {}
    labels: dict[str, float] = {}
    for token in re.split(r"[,|;、/ ]+", value):
        token = token.strip()
        if token in PROBLEM_TYPE_AXES:
            labels[token] = 1.0
    return extract_labels({"labels": labels})


def load_research_maps() -> tuple[dict[str, list[tuple[int, Mapping[str, Any], str]]], dict[str, list[tuple[int, Mapping[str, Any], str]]]]:
    """Load candidate records and evidence maps with explicit source priority."""

    candidates: dict[str, list[tuple[int, Mapping[str, Any], str]]] = defaultdict(list)
    evidence: dict[str, list[tuple[int, Mapping[str, Any], str]]] = defaultdict(list)

    candidate_specs = (
        # Independent historical gap research is exact-keyed and carries a
        # direct QOJ problem page plus contest/alias evidence.  Keep it above
        # the older broad crawls, while allowing a later manual override or
        # final link review to supersede it.
        ("research-historical-gaps-v2.json", 159),
        ("research-historical-gaps.json", 158),
        ("research-newest-gaps.json", 157),
        ("builder-2026-gaps.json", 120),
        ("builder-2026-v2.json", 110),
        ("builder-2025.json", 110),
        ("builder-2024.json", 110),
        ("builder-2023.json", 110),
        ("builder-2022.json", 110),
        ("builder-2026.json", 40),
    )
    for filename, priority in candidate_specs:
        payload = read_json(AUDIT_ROOT / filename, {})
        if isinstance(payload, Mapping):
            records = payload.get("records")
            if not isinstance(records, list):
                records = payload.get("candidates")
        else:
            records = []
        for record in records if isinstance(records, list) else []:
            if not isinstance(record, Mapping):
                continue
            contest = clean_text(record.get("contestKey"))
            alias = clean_text(record.get("alias"))
            if contest and alias:
                candidates[key_for(contest, alias)].append((priority, record, filename))

    # New mirror crawls are kept in a separate, reviewable artifact.  These
    # records are keyed by the exact SRK contest slug and alias; no fuzzy title
    # matching is allowed here.  Atuer is the strongest fallback because its
    # contest page exposes a direct statement URL.  Codeforces Gym records are
    # accepted only as an exact dashboard alias match.  Editorial candidates
    # sit between the two and still retain their QOJ mirror evidence.
    external = read_json(EXTERNAL_CANDIDATES_PATH, {})
    external_records = external.get("records", []) if isinstance(external, Mapping) else []
    for record in external_records if isinstance(external_records, list) else []:
        if not isinstance(record, Mapping):
            continue
        contest = clean_text(record.get("contestKey"))
        alias = clean_text(record.get("alias"))
        if not contest or not alias:
            continue
        source_kind = clean_text(record.get("sourceKind")) or "external"
        normalized_contest = contest.replace("__", "/")
        priority = 145 if source_kind == "atuer-contest" else 132
        # These are explicit, exact Gym assignments (see
        # build_external_problem_candidates.py).  They outrank a shared QOJ
        # tag only for the listed combined/misreferenced contests; QOJ remains
        # the normal primary source everywhere else.
        if source_kind == "codeforces-gym":
            expected_gym = CF_IDENTITY_OVERRIDES.get(normalized_contest)
            source_url = clean_text(record.get("sourceUrl")) or ""
            if expected_gym and re.search(rf"/gym/{re.escape(expected_gym)}(?:$|/)", source_url):
                priority = 170
        candidates[key_for(contest.replace("__", "/"), alias)].append(
            (priority, record, "external-problem-candidates.json")
        )

    # A link reviewer may find a direct mirror before the general crawler does.
    # Keep this input exact-keyed and independent from the production files.
    for gap_name, gap_priority in (
        ("reviewer-links-2026-gap-1.json", 148),
        ("reviewer-links-2026-gap-2.json", 149),
        # Each year below was checked independently against a contest page
        # and a direct statement route.  Keep these reports separate from the
        # broad crawlers so a later export cannot silently reintroduce a
        # collection/rank URL.
        ("reviewer-links-2025-gap-1.json", 151),
        ("reviewer-links-2024-gap-1.json", 151),
        ("reviewer-links-2023-2022-gap-1.json", 151),
        ("reviewer-links-final-current-2.json", 159),
        ("reviewer-links-final-current-1.json", 160),
    ):
        gap_review = read_json(AUDIT_ROOT / gap_name, {})
        if isinstance(gap_review, Mapping):
            gap_records = gap_review.get("candidates")
            if not isinstance(gap_records, list):
                gap_records = gap_review.get("records")
            if not isinstance(gap_records, list):
                gap_records = gap_review.get("checkedRows", [])
        else:
            gap_records = []
        for record in gap_records if isinstance(gap_records, list) else []:
            if not isinstance(record, Mapping):
                continue
            if clean_text(record.get("status")) not in {None, "PASS"}:
                continue
            contest = clean_text(record.get("contestKey"))
            alias = clean_text(record.get("alias"))
            if contest and alias:
                candidates[key_for(contest.replace("__", "/"), alias)].append(
                    (gap_priority, record, gap_name)
                )

    # A tag review is allowed to promote only an explicit PASS row.  The
    # reviewer reports intentionally keep unresolved rows for visibility, but
    # those rows must never become a speculative production label.  ``source``
    # is copied to evidence/sourceUrl only when it is a direct statement URL.
    # Two independent reports can therefore be loaded together; the merge
    # keeps the higher-priority reviewed value while retaining all evidence.
    for tag_name, tag_priority in (
        ("reviewer-tags-2026-final-1.json", 152),
        ("reviewer-tags-2025-final-2.json", 152),
        ("reviewer-tags-2024-gap-final-1.json", 154),
        # The current full reports are kept as two independent inputs.  The
        # first report uses its ``records`` array; the second report may use
        # ``checkedRows``.  The old pre-audit report is intentionally omitted
        # so stale classifications cannot silently re-enter the merge.
        ("reviewer-tags-final-current-2-balanced.json", 159),
        ("reviewer-tags-final-current-2-v3.json", 160),
        ("reviewer-tags-final-current-3.json", 162),
        ("reviewer-tags-final-current-1.json", 161),
    ):
        tag_review = read_json(AUDIT_ROOT / tag_name, {})
        checked: Any = []
        if isinstance(tag_review, Mapping):
            checked = tag_review.get("records")
            if not isinstance(checked, list):
                checked = tag_review.get("checkedRows", [])
        for record in checked if isinstance(checked, list) else []:
            if not isinstance(record, Mapping) or clean_text(record.get("status")) != "PASS":
                continue
            raw_key = clean_text(record.get("key"))
            if raw_key and ":" in raw_key:
                contest, alias = raw_key.rsplit(":", 1)
            else:
                contest = clean_text(record.get("contestKey"))
                alias = clean_text(record.get("alias"))
            if not contest or not alias:
                continue
            promoted = dict(record)
            if not promoted.get("sourceUrl") and individual_url(promoted.get("source")):
                promoted["sourceUrl"] = promoted.get("source")
            candidates[key_for(contest.replace("__", "/"), alias)].append(
                (tag_priority, promoted, tag_name)
            )

    # The editorial reviewer uses contest ids for QOJ groups.  Only the
    # contest id that was independently tied to a target slug is promoted;
    # unresolved editorial guesses remain evidence and cannot affect output.
    editorial_contests = {"1794": "icpc/icpc2024/icpc2024preliminary-1"}
    editorial = read_json(AUDIT_ROOT / "editorial-qoj-candidates-reviewer1.json", [])
    for record in editorial if isinstance(editorial, list) else []:
        if not isinstance(record, Mapping) or record.get("unresolved"):
            continue
        contest = editorial_contests.get(str(record.get("contestId")))
        alias = clean_text(record.get("alias"))
        if contest and alias:
            candidates[key_for(contest, alias)].append(
                (140, record, "editorial-qoj-candidates-reviewer1.json")
            )

    # Explicit manual records are the final, human-readable decision point for
    # sources that need a contest identity check (for example a reused problem
    # set or a page whose title is encoded incorrectly).  The file is produced
    # by the audit workflow and is intentionally not inferred from titles.
    manual = read_json(MANUAL_OVERRIDES_PATH, {})
    manual_records = manual.get("records", []) if isinstance(manual, Mapping) else []
    for record in manual_records if isinstance(manual_records, list) else []:
        if not isinstance(record, Mapping):
            continue
        contest = clean_text(record.get("contestKey"))
        alias = clean_text(record.get("alias"))
        if contest and alias:
            candidates[key_for(contest.replace("__", "/"), alias)].append(
                (155, record, "manual-problem-overrides.json")
            )

    # Curated production files are evidence, but builders outrank them.
    manifest = read_json(MANIFEST_PATH, {})
    for key, record in (manifest.get("problems", {}) if isinstance(manifest, Mapping) else {}).items():
        if isinstance(record, Mapping):
            evidence[str(key)].append((60, record, "problem-types-manifest"))
    catalog = read_json(CATALOG_PATH, {})
    for key, record in (catalog.get("problems", {}) if isinstance(catalog, Mapping) else {}).items():
        if isinstance(record, Mapping):
            evidence[str(key)].append((50, record, "problem-catalog"))

    # Research exports use a mixture of exact contest keys and canonical IDs.
    for path in sorted(RESEARCH_ROOT.glob("*.json")):
        if path.name in {"codeforces-gyms-index.json"}:
            continue
        payload = read_json(path, {})
        if path.name.startswith("agent-tags-"):
            priority = 75
        elif path.name.startswith("manual-labels") or path.name.startswith("labels-"):
            priority = 70
        elif path.name.startswith("agent-title-") or path.name.startswith("vjudge-"):
            priority = 65
        else:
            priority = 45
        for explicit_key, record in walk_records(payload):
            if not isinstance(record, Mapping):
                continue
            key = explicit_key
            if not key:
                contest = clean_text(record.get("contestKey"))
                alias = clean_text(record.get("alias"))
                if contest and alias:
                    key = key_for(contest, alias)
            if key:
                # A source key using a canonical QOJ/CF id is not enough to
                # prove that it belongs to this target contest.  Such entries
                # are retained only as evidence when an exact target key is
                # present; this blocks the historical cross-contest bleed from
                # qoj:2058 onto the 2025 Guizhou rows.
                key_text = str(key).replace("__", "/")
                if key_text.startswith(("qoj:", "cf:", "gym:")):
                    continue
                evidence[key_text].append((priority, record, path.name))

    # The title resolution export is a list, outside qoj-research.  It was
    # collected for the newest contests and deliberately records a known CF
    # fallback even when QOJ search returned multiple or mojibake matches.
    # Promote that fallback to the normal candidate shape so URL resolution
    # can use it, while retaining selected QOJ ids as evidence only.
    resolution = read_json(AUDIT_ROOT / "qoj-title-resolution-2026.json", [])
    for record in resolution if isinstance(resolution, list) else []:
        if isinstance(record, Mapping) and record.get("contestKey") and record.get("alias"):
            promoted = dict(record)
            if not promoted.get("problemUrl") and promoted.get("fallbackUrl"):
                promoted["problemUrl"] = promoted.get("fallbackUrl")
            selected = promoted.get("selectedQoj")
            if isinstance(selected, Mapping):
                if not promoted.get("canonicalId") and selected.get("id") is not None:
                    promoted["canonicalId"] = f"qoj:{selected['id']}"
                if not promoted.get("qojUrl") and selected.get("url"):
                    promoted["qojUrl"] = selected.get("url")
            evidence[key_for(str(record["contestKey"]), str(record["alias"]))].append(
                (100, promoted, "qoj-title-resolution-2026.json")
            )

    return candidates, evidence


def load_target() -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    index = read_json(INDEX_PATH, [])
    # The public index also contains historical contests outside this audit
    # window and can be regenerated by the web exporter.  Keep the audit
    # target deterministic by intersecting it with the checked 141-contest
    # inventory produced during the initial crawl.
    target_contests: set[str] = set()
    if TARGET_CONTESTS_PATH.exists():
        raw = TARGET_CONTESTS_PATH.read_bytes()
        for encoding in ("utf-8", "gb18030"):
            try:
                text = raw.decode(encoding)
                break
            except UnicodeDecodeError:
                text = ""
        for line in text.splitlines():
            parts = line.split("\t")
            if len(parts) >= 3 and parts[2].strip():
                target_contests.add(parts[2].strip().replace("__", "/"))
    rows: list[dict[str, Any]] = []
    raw_by_contest: dict[str, dict[str, Any]] = {}
    for item in index if isinstance(index, list) else []:
        if not isinstance(item, Mapping):
            continue
        start = str(item.get("startAt") or "")
        try:
            year = int(start[:4])
        except ValueError:
            continue
        if year not in TARGET_YEARS:
            continue
        contest = str(item.get("contestSlug") or "").replace("__", "/")
        alias = str(item.get("alias") or "")
        if not contest or not alias:
            continue
        if target_contests and contest not in target_contests:
            continue
        row = dict(item)
        row["contestKey"] = contest
        row["year"] = year
        rows.append(row)
        if contest not in raw_by_contest:
            raw_path = RAW_ROOT / (contest + ".srk.json")
            raw_by_contest[contest] = read_json(raw_path, {})
    groups: dict[str, dict[str, Any]] = {}
    for row in rows:
        groups.setdefault(row["contestKey"], row)
    return rows, raw_by_contest, groups


def load_qoj_assignments(target_rows: list[Mapping[str, Any]]) -> dict[str, list[tuple[int, Mapping[str, Any], str]]]:
    """Build high-confidence QOJ candidates from independently checked mappings.

    The assignment file is deliberately separate from the production catalog.
    Its keys use the SRK slug form (``__`` separators), while the merge key uses
    slash-separated contest paths.  We only materialise an assignment when the
    QOJ id count exactly matches the target aliases; this prevents a warm-up or
    partial QOJ tag from being silently shifted onto a full contest.
    """

    # The original crawl has broad year coverage while the expanded crawl
    # fills complete contest groups that were hidden behind the first crawl's
    # pagination.  Union by problem id and prefer a clean title/URL from
    # either source so assignments can safely reference both indexes.
    qoj_problems: dict[str, dict[str, Any]] = {}
    for index_path in (QOJ_INDEX_PATH, QOJ_EXPANDED_INDEX_PATH):
        qoj_payload = read_json(index_path, {})
        problems = qoj_payload.get("problems", {}) if isinstance(qoj_payload, Mapping) else {}
        if not isinstance(problems, Mapping):
            continue
        for raw_id, raw_problem in problems.items():
            if not isinstance(raw_problem, Mapping):
                continue
            qid = str(raw_id)
            current = qoj_problems.setdefault(qid, dict(raw_problem))
            old_title = str(current.get("title") or "").strip()
            new_title = str(raw_problem.get("title") or "").strip()
            if new_title and (not old_title or "\ufffd" in old_title) and "\ufffd" not in new_title:
                current["title"] = new_title
            if not current.get("url") and raw_problem.get("url"):
                current["url"] = raw_problem.get("url")
    assignments = read_json(QOJ_ASSIGNMENTS_PATH, {})
    if not isinstance(assignments, Mapping):
        return {}

    aliases_by_contest: dict[str, list[str]] = defaultdict(list)
    for row in target_rows:
        contest = clean_text(row.get("contestKey"))
        alias = clean_text(row.get("alias"))
        if contest and alias:
            aliases_by_contest[contest].append(alias)

    result: dict[str, list[tuple[int, Mapping[str, Any], str]]] = defaultdict(list)
    for raw_key, assignment in assignments.items():
        if str(raw_key).startswith("_") or not isinstance(assignment, Mapping):
            continue
        contest = str(raw_key).replace("__", "/")
        # Both assignment generators have used ``targetAliases`` and
        # ``aliases`` over time.  The target inventory remains the source of
        # truth for the actual row set; the assignment list is only accepted
        # when its count agrees exactly.
        target_aliases = sorted(set(aliases_by_contest.get(contest, ())), key=alias_sort)
        assigned_aliases = assignment.get("targetAliases", assignment.get("aliases", []))
        if isinstance(assigned_aliases, list):
            assigned_aliases = sorted({clean_text(value) for value in assigned_aliases if clean_text(value)}, key=alias_sort)
            if assigned_aliases and assigned_aliases != target_aliases:
                continue
        raw_ids = assignment.get("problemIds", [])
        ids: list[int] = []
        for value in raw_ids if isinstance(raw_ids, list) else []:
            try:
                qid = int(value)
            except (TypeError, ValueError):
                continue
            if qid not in ids:
                ids.append(qid)
        ids.sort()
        if not target_aliases or len(ids) != len(target_aliases):
            continue
        tag = clean_text(assignment.get("tag")) or "QOJ confirmed contest tag"
        evidence = assignment.get("evidence")
        evidence_text = json.dumps(evidence, ensure_ascii=False, sort_keys=True) if isinstance(evidence, Mapping) else clean_text(evidence)
        for alias, qid in zip(target_aliases, ids):
            item = qoj_problems.get(str(qid))
            if not isinstance(item, Mapping):
                continue
            title = valid_title(item.get("title") or item.get("name"))
            direct = canonical_problem_url(item.get("url") or item.get("problemUrl"))
            # The QOJ index is the source of the problem identity even when its
            # title was stored with a broken legacy encoding.  In that case the
            # title is left empty so a better CF/official title can win.
            record: dict[str, Any] = {
                "title": title,
                "problemUrl": direct,
                "canonicalId": f"qoj:{qid}",
                "sourceUrl": direct,
                "sourceKind": "qoj-index",
                "evidence": f"QOJ public problem index; contestTag={tag}; problemId={qid}." + (f" assignment={evidence_text}" if evidence_text else ""),
                "confidence": 0.96,
            }
            result[key_for(contest, alias)].append((125, record, "qoj-assignments-final.json"))
    return result


def ref_links(raw_contest: Mapping[str, Any]) -> list[str]:
    contest = raw_contest.get("contest") if isinstance(raw_contest, Mapping) else {}
    values = contest.get("refLinks", []) if isinstance(contest, Mapping) else []
    result: list[str] = []
    for item in values if isinstance(values, list) else []:
        value = item.get("link") if isinstance(item, Mapping) else item
        if isinstance(value, str) and value.strip():
            result.append(value.strip())
    return result


def gym_ids(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        for match in re.finditer(r"(?:gym/|contest/)(\d+)", value):
            if match.group(1) not in result:
                result.append(match.group(1))
    return result


def qoj_ids(value: Any) -> list[str]:
    if not isinstance(value, str):
        return []
    return re.findall(r"(?:^|:)qoj:(\d+)", value)


def first_valid(records: Iterable[tuple[int, Mapping[str, Any], str]], field: str) -> tuple[Any, str | None, int]:
    for priority, record, source in sorted(records, key=lambda item: -item[0]):
        value = record.get(field)
        if field == "title":
            value = clean_external_title(value)
        elif field in {"problemUrl", "url", "link"}:
            # Never let a rank board, tutorial, attachment, or contest page
            # win merely because it is non-empty.  ``sourceUrl`` is handled
            # separately because it is allowed to point to a collection as
            # provenance.
            value = canonical_problem_url(value)
        elif field == "sourceUrl":
            value = value if isinstance(value, str) and value.strip() else None
        elif field == "labels":
            value = extract_labels(record)
        elif field == "detailTags":
            try:
                value = normalize_detail_tags(value)
            except (TypeError, ValueError):
                value = []
        if value:
            return value, source, priority
    return None, None, 0


def canonical_from_record(records: list[tuple[int, Mapping[str, Any], str]], key: str) -> str | None:
    for _priority, record, _source in sorted(records, key=lambda item: -item[0]):
        value = clean_text(record.get("canonicalId"))
        if value and not value.startswith(("unknown:", "srk:")):
            # A platform canonical id copied from an attachment/ranklist is
            # not identity evidence by itself.  Keep it only when the same
            # record carries a valid individual statement URL; otherwise a
            # legacy manifest can resurrect a cross-contest mapping.
            if value.startswith(("qoj:", "cf:", "gym:", "cpc:")):
                direct = any(individual_url(record.get(field)) for field in ("problemUrl", "url", "link"))
                if not direct:
                    continue
            return value
    return None


def canonical_for_url(url: str | None, contest: str, alias: str, current: str | None) -> str | None:
    """Return a canonical identity that agrees with the selected URL.

    Older research files contain canonical ids copied from a QOJ tag even
    when the URL belongs to another contest.  A direct URL is stronger
    identity evidence than that stale id, so normalize the id from the URL
    before writing production data.
    """

    if not url:
        return current
    parsed = urlparse(url)
    host = parsed.netloc.lower().split(":", 1)[0]
    path = unquote(parsed.path.rstrip("/")).lower()
    if host.endswith("qoj.ac") or host.endswith("ucup.ac"):
        match = re.search(r"/problem/(\d+)$", path)
        if match:
            return f"qoj:{match.group(1)}"
    if host.endswith("codeforces.com"):
        match = re.search(r"/gym/(\d+)/problem/([a-z0-9][a-z0-9_-]*)$", path)
        if match:
            return f"cf:{match.group(1)}:{match.group(2).upper()}"
        match = re.search(r"/contest/(\d+)/problem/([a-z0-9][a-z0-9_-]*)$", path)
        if match:
            return f"cf-contest:{match.group(1)}:{match.group(2).upper()}"
    if host.endswith("nowcoder.com"):
        match = re.search(r"/acm/contest/(\d+)/([a-z0-9][a-z0-9_-]*)$", path)
        if match:
            return f"nowcoder:{match.group(1)}:{match.group(2).upper()}"
        match = re.search(r"/acm/problem/([a-z0-9][a-z0-9_-]*)$", path)
        if match:
            return f"nowcoder:problem:{match.group(1).upper()}"
    if host.endswith("atuer.cn"):
        if re.fullmatch(r"/p/[a-z0-9][a-z0-9_-]*", path):
            return f"atuer:{contest}:{alias.upper()}"
    return current


def source_url_from_records(records: list[tuple[int, Mapping[str, Any], str]]) -> str | None:
    for field in ("sourceUrl", "problemUrl", "url", "link"):
        value, _source, _priority = first_valid(records, field)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def build_external_maps() -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    """Return qoj contest pages, CF titles, and exact title/link records."""
    qoj_pages = read_json(AUDIT_ROOT / "qoj-contest-pages-2022-2026.json", {})
    qoj_map: dict[str, dict[str, Any]] = {}
    if isinstance(qoj_pages, Mapping):
        for contest_id, page in qoj_pages.items():
            if isinstance(page, Mapping):
                qoj_map[str(contest_id)] = dict(page)
    cf_titles = read_json(RESEARCH_ROOT / "codeforces-problem-titles.json", {})
    cf_map = {str(k): v for k, v in cf_titles.items() if isinstance(v, Mapping)} if isinstance(cf_titles, Mapping) else {}
    # The independent title pass stores the same Gym→alias mapping in a
    # separate file.  Merge it in so a direct CF statement can rescue rows
    # whose SRK contest reference was lost.
    agent_cf = read_json(RESEARCH_ROOT / "agent-title-cf.json", {})
    if isinstance(agent_cf, Mapping):
        for raw_key, value in agent_cf.items():
            key = str(raw_key)
            if ":" not in key or not isinstance(value, Mapping):
                continue
            gym, alias = key.split(":", 1)
            if not gym.isdigit():
                continue
            bucket = cf_map.setdefault(gym, {})
            if isinstance(bucket, Mapping):
                bucket = dict(bucket)
                cf_map[gym] = bucket
            # Prefer a record carrying a direct statement URL over the older
            # title-only value from codeforces-problem-titles.json.
            existing = bucket.get(alias)
            if not existing or isinstance(existing, str) or value.get("problemUrl") or value.get("url"):
                bucket[alias] = dict(value)
    exact: dict[str, dict[str, Any]] = {}
    for filename in ("agent-title-cf.json", "agent-title-qoj.json", "agent-title-oj.json"):
        payload = read_json(RESEARCH_ROOT / filename, {})
        if isinstance(payload, Mapping):
            for key, value in payload.items():
                if isinstance(value, Mapping):
                    exact[str(key)] = dict(value)
    return qoj_map, cf_map, exact


def qoj_page_record(qoj_map: Mapping[str, Mapping[str, Any]], qid: str, alias: str) -> Mapping[str, Any] | None:
    page = qoj_map.get(str(qid))
    if not isinstance(page, Mapping) or page.get("status") not in {None, "ok"}:
        return None
    for problem in page.get("problems", []) if isinstance(page.get("problems"), list) else []:
        if isinstance(problem, Mapping) and str(problem.get("alias")) == alias:
            return problem
    return None


def derive_url(
    contest_key: str,
    alias: str,
    records: list[tuple[int, Mapping[str, Any], str]],
    raw: Mapping[str, Any],
    canonical: str | None,
    qoj_map: Mapping[str, Mapping[str, Any]],
    cf_map: Mapping[str, Mapping[str, Any]],
    exact_titles: Mapping[str, Mapping[str, Any]],
) -> tuple[str | None, str]:
    # Candidate and curated direct URLs first, with strict filtering.
    for priority, record, source in sorted(records, key=lambda item: -item[0]):
        for field in ("problemUrl", "url", "link"):
            direct = canonical_problem_url(record.get(field))
            if direct:
                return direct, f"{source}:{field}"

    # A successful QOJ/UCUP contest scrape has authoritative per-problem URLs.
    for qid in qoj_ids(canonical):
        problem = qoj_page_record(qoj_map, qid, alias)
        if isinstance(problem, Mapping):
            direct = canonical_problem_url(problem.get("url") or problem.get("problemUrl"))
            if direct:
                return direct, f"qoj-contest-pages:{qid}"

    refs = ref_links(raw)
    # Exact title maps often carry a direct CF URL even when SRK retained only
    # a rank board.  Try them before deriving from the contest reference.
    for qid in qoj_ids(canonical):
        for key in (f"qoj:{qid}:{alias}", f"qoj:{qid}"):
            item = exact_titles.get(key)
            if isinstance(item, Mapping):
                direct = canonical_problem_url(item.get("problemUrl") or item.get("url"))
                if direct:
                    return direct, f"qoj-title-map:{key}"
    for gym in gym_ids(refs):
        item = cf_map.get(gym, {}).get(alias) if isinstance(cf_map.get(gym), Mapping) else None
        if isinstance(item, str):
            title_item = {"problemUrl": item}
        else:
            title_item = item if isinstance(item, Mapping) else {}
        direct = canonical_problem_url(title_item.get("problemUrl") or title_item.get("url"))
        if direct:
            return direct, f"cf-title-map:{gym}"

    # Derive only platforms whose individual URL grammar is stable.
    for ref in refs:
        parsed = urlparse(ref)
        host = parsed.netloc.lower()
        parts = [part for part in parsed.path.split("/") if part]
        if host.endswith("codeforces.com"):
            match = re.search(r"/gym/(\d+)", parsed.path)
            if match:
                return f"https://codeforces.com/gym/{match.group(1)}/problem/{alias}", "derived-codeforces"
        if host.endswith("nowcoder.com"):
            match = re.search(r"/acm/contest/(\d+)", parsed.path)
            if match:
                return f"https://ac.nowcoder.com/acm/contest/{match.group(1)}/{alias}", "derived-nowcoder"
        if host.endswith("qoj.ac"):
            match = re.search(r"/contest/(\d+)", parsed.path)
            if match:
                problem = qoj_page_record(qoj_map, match.group(1), alias)
                if isinstance(problem, Mapping):
                    direct = canonical_problem_url(problem.get("url") or problem.get("problemUrl"))
                    if direct:
                        return direct, f"qoj-contest-ref:{match.group(1)}"
    # A two-part qoj:<numeric-id> is an individual statement identity.
    if canonical and re.fullmatch(r"qoj:\d+", canonical):
        return f"https://qoj.ac/problem/{canonical.split(':', 1)[1]}", "derived-qoj-problem"
    return None, "unresolved"


def infer_labels(title: str | None, evidence: str | None, detail_tags: list[str]) -> dict[str, float]:
    text = " ".join(x for x in (title, evidence) if x).lower()
    hits: list[str] = []
    keyword_axes = (
        ("geometry", ("geometry", "几何", "polygon", "triangle", "rectangle", "circle", "点积", "叉积", "凸包")),
        ("string", ("string", "字符串", "prefix", "suffix", "kmp", "trie", "hash", "回文", "字典")),
        ("graph", ("graph", "图论", "tree", "树", "path", "最短路", "flow", "matching", "mst", "连通")),
        ("dp", ("dynamic programming", "动态规划", " dp", "dp ", "knapsack", "背包", "状态转移", "记忆化")),
        ("math", ("math", "数学", "number theory", "数论", "probability", "概率", "组合", "mod", "xor", "gcd")),
        ("dataStructure", ("data structure", "数据结构", "segment tree", "线段树", "fenwick", "树状数组", "heap", "堆", "dsu", "并查集")),
        ("basic", ("simulation", "模拟", "construct", "构造", "签到", "implementation", "实现")),
    )
    for axis, words in keyword_axes:
        if any(word in text for word in words):
            hits.append(axis)
    for tag in detail_tags:
        if tag in {"几何", "凸包", "旋转卡壳", "半平面交", "叉积与方向"}:
            hits.append("geometry")
        elif tag in {"字符串哈希", "KMP", "AC自动机", "后缀数组", "后缀自动机", "回文算法", "字典树"}:
            hits.append("string")
        elif tag in {"DFS/BFS", "最短路", "最小生成树", "拓扑排序", "强连通分量", "网络流", "匹配", "树链剖分", "最近公共祖先"}:
            hits.append("graph")
        elif tag in {"树形DP", "换根DP", "背包DP", "区间DP", "状压DP", "数位DP", "概率DP", "计数DP", "记忆化搜索", "插头DP"}:
            hits.append("dp")
        elif tag in {"线段树", "树状数组", "堆", "单调栈", "单调队列", "并查集", "莫队", "分块", "李超树"}:
            hits.append("dataStructure")
        elif tag in {"数论", "素数筛", "最大公约数", "组合数学", "容斥", "生成函数", "矩阵快速幂", "线性代数", "概率与期望", "博弈论", "计数", "模运算", "莫比乌斯反演", "质因数分解"}:
            hits.append("math")
        elif tag in {"模拟", "构造", "贪心", "排序", "二分查找", "双指针", "前缀和", "差分", "枚举", "分治", "递归", "交互", "位运算"}:
            hits.append("basic")
    ordered: list[str] = []
    for axis in hits:
        if axis not in ordered:
            ordered.append(axis)
    if not ordered:
        return {}
    ordered = ordered[:2]
    if len(ordered) == 1:
        return {ordered[0]: 1.0}
    return {ordered[0]: 0.6, ordered[1]: 0.4}


def infer_detail_tags(title: str | None, evidence: str | None, labels: Mapping[str, float]) -> list[str]:
    text = " ".join(x for x in (title, evidence) if x).lower()
    hits: list[str] = []

    def keyword_present(keyword: str) -> bool:
        """Match ASCII technique names as words, not as arbitrary substrings.

        A plain ``keyword in text`` check turns ``nim`` into a false hit for
        the word ``minimum`` and similarly lets short abbreviations leak into
        unrelated titles.  Chinese phrases still use substring matching,
        while ASCII names use identifier boundaries.
        """

        keyword = str(keyword).strip().lower()
        if not keyword:
            return False
        if any(ord(char) > 127 for char in keyword):
            return keyword in text
        pattern = rf"(?<![a-z0-9_]){re.escape(keyword)}(?![a-z0-9_])"
        return re.search(pattern, text, flags=re.IGNORECASE) is not None

    keyword_tags = (
        (("线段树", "segment tree"), "线段树"),
        (("树状数组", "fenwick", "bit tree"), "树状数组"),
        (("并查集", "dsu", "disjoint set"), "并查集"),
        (("最小生成树", "minimum spanning tree", "mst"), "最小生成树"),
        (("最短路", "shortest path", "dijkstra", "最短路径"), "最短路"),
        (("网络流", "max flow", "min-cost flow"), "网络流"),
        (("匹配", "matching"), "匹配"),
        (("拓扑", "topological"), "拓扑排序"),
        (("dfs", "bfs", "深度优先", "广度优先"), "DFS/BFS"),
        (("lca", "最近公共祖先"), "最近公共祖先"),
        (("树链剖分", "heavy-light"), "树链剖分"),
        (("kmp", "prefix-function"), "KMP"),
        (("后缀自动机", "suffix automaton", "sam"), "后缀自动机"),
        (("后缀数组", "suffix array"), "后缀数组"),
        (("回文", "palindrome"), "回文算法"),
        (("trie", "字典树"), "字典树"),
        (("hash", "哈希"), "哈希表"),
        (("二分", "binary search"), "二分查找"),
        (("双指针", "two pointers", "two-pointer"), "双指针"),
        (("前缀和", "prefix sum"), "前缀和"),
        (("差分", "difference array"), "差分"),
        (("贪心", "greedy"), "贪心"),
        (("构造", "construct"), "构造"),
        (("模拟", "simulation"), "模拟"),
        (("背包", "knapsack"), "背包DP"),
        (("区间 dp", "interval dp"), "区间DP"),
        (("状压", "bitmask dp"), "状压DP"),
        (("数位 dp", "digit dp"), "数位DP"),
        (("概率 dp", "probability dp"), "概率DP"),
        (("动态规划", "dynamic programming", " dp ", "dp"), "记忆化搜索"),
        (("凸包", "convex hull"), "凸包"),
        (("叉积", "cross product", "点积"), "叉积与方向"),
        (("几何", "geometry", "triangle", "rectangle"), "叉积与方向"),
        (("数论", "number theory", "gcd", "质数", "prime"), "数论"),
        (("组合", "combinator", "容斥", "counting"), "组合数学"),
        (("概率", "probability", "期望"), "概率与期望"),
        (("博弈", "game theory", "nim"), "博弈论"),
        (("矩阵", "matrix exponent"), "矩阵快速幂"),
        (("xor", "异或", "位运算"), "位运算"),
    )
    for words, tag in keyword_tags:
        if any(keyword_present(word) for word in words) and tag not in hits:
            hits.append(tag)
    if not hits:
        for axis in labels:
            fallback = {
                "dataStructure": "哈希表",
                "graph": "DFS/BFS",
                "dp": "记忆化搜索",
                "math": "数论",
                "string": "字符串哈希",
                "geometry": "叉积与方向",
                "basic": "模拟",
            }.get(axis)
            if fallback:
                hits.append(fallback)
                break
    try:
        # Keep every canonical technique supported by the title/evidence.  The
        # coarse seven-axis field is intentionally limited elsewhere, but the
        # fine-grained field must not discard a third (or later) technique.
        return normalize_detail_tags(hits)
    except ValueError:
        return []


def build() -> dict[str, Any]:
    target_rows, raw_by_contest, contest_rows = load_target()
    candidates, evidence = load_research_maps()
    # Inject the independently mapped QOJ contest groups before resolution so
    # their per-problem titles, canonical ids, and direct statement URLs are
    # available to every downstream field.  The loader only emits exact
    # count-matched assignments, leaving ambiguous/warm-up groups queued for
    # the later review pass.
    for key, records in load_qoj_assignments(target_rows).items():
        candidates[key].extend(records)
    qoj_map, cf_map, exact_titles = build_external_maps()
    manifest = read_json(MANIFEST_PATH, {"version": "problem-types-audited-v1", "axes": [], "problems": {}})
    catalog = read_json(CATALOG_PATH, {"version": "problem-catalog-audited-v1", "problems": {}})
    manifest_problems = dict(manifest.get("problems", {})) if isinstance(manifest, Mapping) else {}
    catalog_problems = dict(catalog.get("problems", {})) if isinstance(catalog, Mapping) else {}

    # Parse the broad pre-merge summary as a low-priority exact map.  It often
    # contains a title or URL that is still useful after stricter filtering.
    summary_path = AUDIT_ROOT / "target-summary.tsv"
    if summary_path.exists():
        with summary_path.open("r", encoding="utf-8", newline="") as handle:
            for item in csv.DictReader(handle, delimiter="\t"):
                slug = clean_text(item.get("slug"))
                alias = clean_text(item.get("alias"))
                if not slug or not alias:
                    continue
                contest = slug.replace("__", "/")
                record: dict[str, Any] = {
                    "title": item.get("title"),
                    "problemUrl": item.get("url"),
                    "canonicalId": item.get("cid"),
                    "labels": parse_label_string(item.get("labels")),
                    "sourceUrl": item.get("rawlink"),
                    "evidence": item.get("evidence"),
                }
                evidence[key_for(contest, alias)].append((35, record, "target-summary.tsv"))

    built: dict[str, dict[str, Any]] = {}
    for row in target_rows:
        contest = row["contestKey"]
        alias = row["alias"]
        key = key_for(contest, alias)
        records = list(candidates.get(key, ())) + list(evidence.get(key, ()))
        raw = raw_by_contest.get(contest, {})
        raw_problem = {}
        for item in raw.get("problems", []) if isinstance(raw, Mapping) else []:
            if isinstance(item, Mapping) and str(item.get("alias")) == alias:
                raw_problem = dict(item)
                break

        raw_title = valid_title(raw_problem.get("title"))
        if raw_title:
            # Keep the exact SRK title available to resolution.  It outranks
            # legacy title-only research, while an independently checked
            # Atuer/QOJ/Codeforces record still wins when it has a stronger
            # contest-specific identity.
            records.append((142, {"title": raw_title, "evidence": "SRK exact alias/title row."}, "srk-exact-title"))

        title, title_source, title_priority = first_valid(records, "title")
        # qoj contest page title and exact external title maps.
        canonical = canonical_from_record(records, key)
        if not title and canonical:
            for qid in qoj_ids(canonical):
                problem = qoj_page_record(qoj_map, qid, alias)
                if isinstance(problem, Mapping):
                    title = valid_title(problem.get("title") or problem.get("name"))
                    if title:
                        title_source = f"qoj-contest-pages:{qid}"
                        break
        if not title:
            # Exact maps use either contest:alias or qoj:<id>:alias keys.
            for map_key in (key, *(f"qoj:{qid}:{alias}" for qid in qoj_ids(canonical))):
                item = exact_titles.get(map_key)
                if isinstance(item, Mapping):
                    title = valid_title(item.get("title") or item.get("name"))
                    if title:
                        title_source = f"title-map:{map_key}"
                        break
        if not title:
            refs = ref_links(raw)
            for gym in gym_ids(refs):
                item = cf_map.get(gym, {}).get(alias) if isinstance(cf_map.get(gym), Mapping) else None
                if isinstance(item, Mapping):
                    title = valid_title(item.get("title") or item.get("name"))
                elif isinstance(item, str):
                    title = valid_title(item)
                if title:
                    title_source = f"cf-title-map:{gym}"
                    break
        if not title:
            title = valid_title(raw_problem.get("title"))
            if title:
                title_source = "srk"

        # The raw SRK row is an exact alias/title pair from the source
        # inventory.  It is intentionally considered after audited mirror
        # candidates but before the legacy evidence maps, so a stale QOJ tag
        # cannot replace a valid official title.  Do this as a local fallback
        # rather than mutating the shared candidate maps.
        if not title and raw_title:
            title = raw_title
            title_source = "srk-exact-title"

        labels, labels_source, labels_priority = first_valid(records, "labels")
        if not isinstance(labels, Mapping):
            labels = {}
        labels = extract_labels({"labels": labels})
        detail_tags, detail_source, detail_priority = first_valid(records, "detailTags")
        detail_tags = detail_tags if isinstance(detail_tags, list) else []
        if not detail_tags:
            # Existing label/evidence maps may have no fine-grained field.
            evidence_text = None
            for _p, rec, _s in sorted(records, key=lambda item: -item[0]):
                if clean_text(rec.get("evidence")):
                    evidence_text = clean_text(rec.get("evidence"))
                    break
            detail_tags = infer_detail_tags(title, evidence_text, labels)
            detail_source = "deterministic-title-evidence-inference" if detail_tags else None
        if not labels:
            evidence_text = None
            for _p, rec, _s in sorted(records, key=lambda item: -item[0]):
                if clean_text(rec.get("evidence")):
                    evidence_text = clean_text(rec.get("evidence"))
                    break
            labels = infer_labels(title, evidence_text, detail_tags)
            labels_source = "deterministic-title-evidence-inference" if labels else None
        labels = extract_labels({"labels": labels})

        problem_url, url_source = derive_url(
            contest, alias, records, raw, canonical, qoj_map, cf_map, exact_titles
        )
        # Reconcile a stale canonical id with the actual direct statement
        # selected above.  This is what prevents e.g. a qoj:<old-contest>
        # identity from being paired with a Codeforces/Atuer URL.
        canonical = canonical_for_url(problem_url, contest, alias, canonical)
        source_url = source_url_from_records(records) or problem_url
        evidence_text = None
        for _p, rec, _s in sorted(records, key=lambda item: -item[0]):
            text = clean_text(rec.get("evidence"))
            if text:
                evidence_text = text
                break
        pieces = []
        if title_source:
            pieces.append(f"title={title_source}")
        if url_source:
            pieces.append(f"link={url_source}")
        if labels_source:
            pieces.append(f"tags={labels_source}")
        if evidence_text:
            pieces.append(evidence_text)
        if not pieces:
            pieces.append("No independently confirmed source yet; queued for review.")
        canonical = canonical or f"event:{contest}:{alias}"
        status = "classified" if labels else "unknown"
        confidence_values = []
        for _p, rec, _s in sorted(records, key=lambda item: -item[0]):
            raw_conf = rec.get("confidence")
            if isinstance(raw_conf, (int, float)) and math.isfinite(float(raw_conf)):
                confidence_values.append(float(raw_conf))
        confidence = max(0.2, min(0.99, confidence_values[0] if confidence_values else (0.55 if labels else 0.2)))
        unresolved: list[str] = []
        if not title:
            unresolved.append("title not confirmed by an authoritative source")
        if not problem_url:
            unresolved.append("individual problem URL not confirmed; collection links excluded")
        if not labels:
            unresolved.append("broad algorithm tag not confirmed")
        if not detail_tags:
            unresolved.append("specific algorithm tag not confirmed")
        built[key] = {
            "contestKey": contest,
            "contestSlug": contest_slug(contest),
            "year": row["year"],
            "alias": alias,
            "title": title,
            "problemUrl": problem_url,
            "canonicalId": canonical,
            "labels": labels,
            "broadTags": [
                {"key": axis, "label": PROBLEM_TYPE_LABELS[axis], "weight": round(weight, 6)}
                for axis, weight in labels.items()
            ],
            "detailTags": detail_tags,
            "status": status,
            "confidence": round(confidence, 4),
            "sourceKind": url_source,
            "sourceUrl": source_url,
            "evidence": " ".join(pieces),
            "unresolvedEvidence": "; ".join(unresolved) if unresolved else None,
            "review": {"tags": {"status": "pending", "reviewers": []}, "links": {"status": "pending", "reviewers": []}},
        }

    # Resolve accidental canonical collisions only when they refer to different
    # statements.  Same URL+title is a legitimate reused problem set.
    by_canonical: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in built.values():
        by_canonical[record["canonicalId"]].append(record)
    for canonical, records in by_canonical.items():
        identities = {(r.get("problemUrl"), r.get("title")) for r in records}
        if len(records) > 1 and len(identities) > 1:
            for record in records:
                record["canonicalId"] = f"event:{record['contestKey']}:{record['alias']}"

    # A row whose statement identity could not be resolved still needs a stable,
    # non-empty canonical id: the manifest validator (and the skill model that
    # consumes it) requires one.  Use the same event-scoped fallback that the
    # published contest documents already carry.
    for record in built.values():
        if not record.get("canonicalId"):
            record["canonicalId"] = f"event:{record['contestKey']}:{record['alias']}"

    # Update production manifest and title/link catalog for target rows only.
    for key, record in built.items():
        manifest_problems[key] = {
            "canonicalId": record["canonicalId"],
            "alias": record["alias"],
            "labels": record["labels"],
            "detailTags": record["detailTags"],
            "confidence": record["confidence"],
            "status": record["status"],
            "sourceUrl": record["sourceUrl"],
            "evidence": record["evidence"],
            "unresolvedEvidence": record["unresolvedEvidence"],
        }
        catalog_problems[key] = {
            "title": record["title"],
            "problemUrl": record["problemUrl"],
            "canonicalId": record["canonicalId"],
            "sourceUrl": record["sourceUrl"],
            "sourceKind": record["sourceKind"],
            "evidence": record["evidence"],
        }

    manifest_out = dict(manifest) if isinstance(manifest, Mapping) else {}
    manifest_out["version"] = "problem-types-audited-v2"
    manifest_out["sourceWindow"] = "2022-2026; two-pass metadata audit"
    manifest_out["problems"] = manifest_problems
    catalog_out = dict(catalog) if isinstance(catalog, Mapping) else {}
    catalog_out["version"] = "problem-catalog-audited-v2"
    catalog_out["problems"] = catalog_problems
    write_json(MANIFEST_PATH, manifest_out)
    write_json(CATALOG_PATH, catalog_out)

    # One reviewable document per contest, as requested by the user.
    generated_at = datetime.now(timezone.utc).isoformat()
    grouped: dict[tuple[int, str], list[dict[str, Any]]] = defaultdict(list)
    for record in built.values():
        grouped[(record["year"], record["contestKey"])].append(record)
    contest_index: list[dict[str, Any]] = []
    for (year, contest), problems in sorted(grouped.items(), key=lambda item: (-item[0][0], item[0][1])):
        row = contest_rows[contest]
        problems.sort(key=lambda item: alias_sort(item["alias"]))
        payload = {
            "schemaVersion": "problem-metadata-v1",
            "generatedAt": generated_at,
            "year": year,
            "contestKey": contest,
            "contestSlug": contest_slug(contest),
            "contestName": clean_text(row.get("contestTitle")) or contest,
            "startAt": row.get("startAt"),
            "sourcePolicy": {"primary": "QOJ/UCUP", "fallback": "Codeforces/official"},
            "review": {
                "required": {"tags": 2, "links": 2},
                "tags": {"status": "pending", "reviewers": []},
                "links": {"status": "pending", "reviewers": []},
            },
            "problems": problems,
        }
        path = OUT_ROOT / str(year) / f"{contest_slug(contest)}.json"
        write_json(path, payload)
        contest_index.append({"year": year, "contestKey": contest, "contestSlug": contest_slug(contest), "contestName": payload["contestName"], "path": str(path.relative_to(ROOT)).replace("\\", "/"), "problemCount": len(problems)})

    write_json(
        OUT_ROOT / "index.json",
        {"schemaVersion": "problem-metadata-index-v1", "generatedAt": generated_at, "source": "web/public/data/problems-index.json", "contests": contest_index},
    )

    # A machine-readable merge report drives the progress page and reviewer
    # agents without making them parse every contest document.
    unresolved = [r for r in built.values() if r["unresolvedEvidence"]]
    report = {
        "schemaVersion": "problem-audit-merge-v1",
        "generatedAt": generated_at,
        "targetRows": len(target_rows),
        "targetContests": len(grouped),
        "resolved": {"titles": sum(bool(r["title"]) for r in built.values()), "links": sum(bool(r["problemUrl"]) for r in built.values()), "labels": sum(bool(r["labels"]) for r in built.values()), "detailTags": sum(bool(r["detailTags"]) for r in built.values())},
        "unresolvedCount": len(unresolved),
        "unresolved": [{"key": f"{r['contestKey']}:{r['alias']}", "reason": r["unresolvedEvidence"]} for r in unresolved],
    }
    write_json(AUDIT_ROOT / "merge-report.json", report)
    return report


if __name__ == "__main__":
    result = build()
    print(json.dumps(result, ensure_ascii=False, indent=2))
