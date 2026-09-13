#!/usr/bin/env python3
"""Build deterministic reviewer-pair inputs for the next audit round.

The production finalizer accepts exactly two named reports per field.  New
review rounds are produced in year partitions, so this small bridge combines
those independent pairs with the already published pair without treating a
single new PASS as sufficient evidence.  A row is copied from a new round
only when both reports in that round say PASS and agree on the complete value.
Rows without a new consensus keep the existing pair untouched.  Conflicts are
written to a separate report for the root agent to inspect; they are never
silently merged.

This script only writes review artifacts.  It does not modify ``data/problem``
or any web export.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
AUDIT_ROOT = ROOT / "work" / "problem-audit"
ROOT_ADJUDICATION_PATH = AUDIT_ROOT / "root-adjudications-round2.json"

# Batch-registered reviewer pairs.  Long audits are executed contest by contest;
# each finished batch appends its (label, report-a, report-b) triples here so the
# hand-maintained ``ROUND_SPECS`` above stays readable.  A missing manifest (for
# example under a test's temporary audit root) simply contributes no rounds.
GENERATED_ROUNDS_PATH = "round-pairs.json"

# The product schema caps the *coarse* axes at two.  Fine-grained
# ``detailTags`` has no arbitrary count cap: keep every canonical technique
# that the independent reviewers can support from the official tutorial.

# A small number of independent reports use a platform slug instead of the
# canonical contest key in the target inventory.  Normalize those aliases at
# the boundary so a pair is joined by contest + problem alias, never by the
# reviewer-specific spelling.
CONTEST_KEY_ALIASES = {
    "cf-gym-104725": "ccpc/ccpc2023/ccpc2023ladies",
    "ccpc/icpc2022final": "ccpc/ccpc2022/ccpc2022final",
    # Official-PDF reviewers sometimes identify a QOJ contest by its numeric
    # contest id. Normalize those ids before pairing rows.
    "qoj:3766": "icpc/icpc2026/icpc2026invitational-xi_an",
    "qoj:3784": "ccpc/ccpc2026/ccpc2026invitational-fuzhou",
    "qoj:3756": "provincial/js/jscpc11th",
    "qoj:3799": "icpc/icpc2026/icpc2026invitational-wuhan",
    "ccpc/ccpc2024/ccpc2024preliminary-2": "icpc/icpc2024/icpc2024preliminary-2",
    "icpc/2024/icpc2024invitational-wuhan": "icpc/icpc2024/icpc2024invitational-wuhan",
}


BASE_SPECS = {
    "links": (
        ("reviewer-links-final-current-1.json", "links-reviewer-1"),
        ("reviewer-links-final-current-2.json", "links-reviewer-2"),
    ),
    "tags": (
        ("reviewer-tags-final-current-1.json", "tags-reviewer-1"),
        ("reviewer-tags-final-current-2-strict.json", "tags-reviewer-2"),
    ),
}

# Each tuple is (round label, report A, report B).  Reports are optional while
# an agent is still working; an incomplete pair is simply skipped.
ROUND_SPECS = {
    "links": (
        (
            "2026-2025",
            "reviewer-links-round2-a-2026-2025.json",
            "reviewer-links-round2-b-2026-2025.json",
        ),
        (
            "2024",
            "reviewer-links-round2-a-2024.json",
            "reviewer-links-round2-b-2024.json",
        ),
        (
            "2023-2022",
            "reviewer-links-round2-a-2023-2022.json",
            "reviewer-links-round2-b-2023-2022.json",
        ),
        (
            "2024-preliminary-2-gap",
            "reviewer-links-gap-2024prelim2-a.json",
            "reviewer-links-gap-2024prelim2-b.json",
        ),
        (
            "2023-ladies-gap",
            "reviewer-links-gap-2023ladies-a.json",
            "reviewer-links-gap-2023ladies-b.json",
        ),
        # Extra link pass covering rows that were still unresolved after the
        # broad year-partition audits.  The pair is intentionally kept
        # separate so both public-source reviews can be inspected before it
        # contributes to the synthetic consensus reports.
        (
            "extra-gap-2025-2024",
            "reviewer-links-gap-extra-agent.json",
            "reviewer-links-gap-extra-reviewer.json",
        ),
        (
            "2026-gap-qoj-henan-northeast",
            "reviewer-links-2026-gap-2.json",
            "reviewer-links-2026-gap-2-second.json",
        ),
        (
            "2026-front-guizhou-beijing",
            "reviewer-links-2026-front-research.json",
            "reviewer-links-2026-front-second.json",
        ),
        (
            "2025-gap",
            "reviewer-links-2025-gap-a.json",
            "reviewer-links-2025-gap-b.json",
        ),
        (
            "historical-gap-2024",
            "reviewer-links-historical-gap-a.json",
            "reviewer-links-historical-gap-b.json",
        ),
        (
            "2026-remaining-direct-pages",
            "reviewer-links-2026-remaining-a.json",
            "reviewer-links-2026-remaining-b.json",
        ),
        (
            "2026-guizhou-independent",
            "reviewer-links-2026-guizhou-independent-a-retry.json",
            "reviewer-links-2026-guizhou-independent-b.json",
        ),
        (
            "2026-qinhuangdao-independent",
            "reviewer-links-2026-qinhuangdao-independent-a.json",
            "reviewer-links-2026-qinhuangdao-independent-b.json",
        ),
        (
            "2026-wuhan-shenzhen-independent",
            "reviewer-links-2026-wuhan-shenzhen-a.json",
            "reviewer-links-2026-wuhan-shenzhen-b.json",
        ),
        (
            "2026-nanchang-beijing-independent",
            "reviewer-links-2026-nanchang-beijing-a.json",
            "reviewer-links-2026-nanchang-beijing-b.json",
        ),
        (
            "2026-nanchang-106551-independent",
            "reviewer-links-2026-nanchang-106551-a.json",
            "reviewer-links-2026-nanchang-106551-b.json",
        ),
        (
            "2026-henan-independent",
            "reviewer-links-2026-ha-a.json",
            "reviewer-links-2026-ha-b.json",
        ),
        (
            "2026-guizhou-recheck",
            "reviewer-links-2026-guizhou-a.json",
            "reviewer-links-2026-guizhou-b.json",
        ),
        (
            "2026-inner-mongolia-recheck",
            "reviewer-links-2026-nm-a.json",
            "reviewer-links-2026-nm-b.json",
        ),
        (
            "2025-ladies-recheck",
            "reviewer-links-2025-ladies-b-retry.json",
            "reviewer-links-2025-ladies-c-backup.json",
        ),
        (
            "2025-hongkong-recheck",
            "reviewer-links-2025-hongkong-a.json",
            "reviewer-links-2025-hongkong-b.json",
        ),
    ),
    "tags": (
        (
            "2026-2025",
            "reviewer-tags-round2-a-2026-2025.json",
            "reviewer-tags-round2-b-2026-2025.json",
        ),
        (
            "2024",
            "reviewer-tags-round2-a-2024.json",
            "reviewer-tags-round2-b-2024.json",
        ),
        (
            "2023-2022",
            "reviewer-tags-round2-a-2023-2022.json",
            "reviewer-tags-round2-b-2023-2022.json",
        ),
        # The first 2024 Shenyang review intentionally used conservative
        # unresolved results, while the tutorial-focused follow-up produced
        # detailed labels.  If a second tutorial-focused reviewer agrees, the
        # C/D pair is an independent two-pass decision for those 13 rows.
        (
            "2024-shenyang-tutorial",
            "reviewer-tags-round2-c-2024.json",
            "reviewer-tags-round2-d-2024.json",
        ),
        (
            "2023-2022-ccpc-final-tutorial",
            "reviewer-tags-round2-c-2023-2022.json",
            "reviewer-tags-round2-d-2023-2022.json",
        ),
        (
            "2023-2022-ccpc-final-tutorial-independent",
            "reviewer-tags-round2-c-2023-2022.json",
            "reviewer-tags-round2-e-2023-2022.json",
        ),
        (
            "2026-official-tutorial",
            "reviewer-tags-2026-official-a.json",
            "reviewer-tags-2026-official-b.json",
        ),
        (
            "2026-guangdong-official-tutorial",
            "reviewer-tags-2026-official-a.json",
            "reviewer-tags-2026-guangdong-c.json",
        ),
        (
            "2025-official-tutorials",
            "reviewer-tags-2025-official-a.json",
            "reviewer-tags-2025-official-b.json",
        ),
        (
            "2026-guizhou-independent",
            "reviewer-tags-2026-guizhou-independent-b-retry.json",
            "reviewer-tags-2026-guizhou-independent-c-retry.json",
        ),
        (
            "2026-qinhuangdao-independent",
            "reviewer-tags-2026-qinhuangdao-independent-a.json",
            "reviewer-tags-2026-qinhuangdao-independent-b.json",
        ),
        (
            "2026-wuhan-shenzhen-independent",
            "reviewer-tags-2026-wuhan-shenzhen-a.json",
            "reviewer-tags-2026-wuhan-shenzhen-b.json",
        ),
        (
            "2026-nanchang-beijing-independent",
            "reviewer-tags-2026-nanchang-beijing-a.json",
            "reviewer-tags-2026-nanchang-beijing-b.json",
        ),
        (
            "2026-hl-jl-independent",
            "reviewer-tags-2026-hl-jl-a.json",
            "reviewer-tags-2026-hl-jl-b.json",
        ),
        (
            "2026-zj-sd-independent",
            "reviewer-tags-2026-zj-sd-a.json",
            "reviewer-tags-2026-zj-sd-b.json",
        ),
        (
            "2026-nanchang-106551-independent",
            "reviewer-tags-2026-nanchang-106551-a.json",
            "reviewer-tags-2026-nanchang-106551-b.json",
        ),
        (
            "2026-henan-tutorial-independent",
            "reviewer-tags-2026-ha-b.json",
            "reviewer-tags-2026-ha-c.json",
        ),
        (
            "2026-guizhou-recheck",
            "reviewer-tags-2026-guizhou-a.json",
            "reviewer-tags-2026-guizhou-b.json",
        ),
        (
            "2026-beijing-nanchang-pending-recheck",
            "reviewer-tags-2026-bj-nc-pending-a.json",
            "reviewer-tags-2026-bj-nc-pending-b.json",
        ),
        (
            "2026-inner-mongolia-recheck",
            "reviewer-tags-2026-nm-a.json",
            "reviewer-tags-2026-nm-b.json",
        ),
        (
            "2026-chongqing-recheck",
            "reviewer-tags-2026-cq-a.json",
            "reviewer-tags-2026-cq-b.json",
        ),
        (
            "2026-jiangsu-recheck",
            "reviewer-tags-2026-js-a.json",
            "reviewer-tags-2026-js-b.json",
        ),
        (
            "2026-northeast-recheck",
            "reviewer-tags-2026-northeast-a.json",
            "reviewer-tags-2026-northeast-b.json",
        ),
        (
            "2026-sichuan-recheck",
            "reviewer-tags-2026-sc-a.json",
            "reviewer-tags-2026-sc-b.json",
        ),
        (
            "2026-guangdong-recheck",
            "reviewer-tags-2026-gd-a.json",
            "reviewer-tags-2026-gd-b.json",
        ),
        (
            "2026-guangxi-recheck",
            "reviewer-tags-2026-gx-a.json",
            "reviewer-tags-2026-gx-b.json",
        ),
        (
            "2026-henan-ccpc-recheck",
            "reviewer-tags-2026-haccpc8th-a.json",
            "reviewer-tags-2026-haccpc-b.json",
        ),
        (
            "2026-ecfinal-pending-recheck",
            "reviewer-tags-2026-ecfinal-a.json",
            "reviewer-tags-2026-ecfinal-b.json",
        ),
        (
            "2025-ladies-recheck",
            "reviewer-tags-2025-ladies-b-retry.json",
            "reviewer-tags-2025-ladies-c-backup.json",
        ),
        (
            "2025-hongkong-recheck",
            "reviewer-tags-2025-hongkong-a.json",
            "reviewer-tags-2025-hongkong-b.json",
        ),
        (
            "2025-nanchang-recheck",
            "reviewer-tags-2025-nanchang-a.json",
            "reviewer-tags-2025-nanchang-b-retry.json",
        ),
        (
            "2025-sichuan-recheck",
            "reviewer-tags-2025-sichuan-a.json",
            "reviewer-tags-2025-sichuan-b.json",
        ),
        (
            "2025-northeast-recheck",
            "reviewer-tags-2025-northeast-a.json",
            "reviewer-tags-2025-northeast-b.json",
        ),
        (
            "2025-gdpre-recheck",
            "reviewer-tags-2025-gdpre-a.json",
            "reviewer-tags-2025-gdpre-b.json",
        ),
        (
            "2025-zhengzhou-recheck",
            "reviewer-tags-2025-zhengzhou-a.json",
            "reviewer-tags-2025-zhengzhou-b.json",
        ),
        (
            "2025-henan-recheck",
            "reviewer-tags-2025-henan-a.json",
            "reviewer-tags-2025-henan-b-retry2.json",
        ),
        (
            "2025-beijing-af-recheck",
            "reviewer-tags-2025-beijing-af-a-retry.json",
            "reviewer-tags-2025-beijing-af-b.json",
        ),
        (
            "2025-shanghai-af-recheck",
            "reviewer-tags-2025-shanghai-af-a.json",
            "reviewer-tags-2025-shanghai-af-b.json",
        ),
        (
            "2025-jiangxi-af-recheck",
            "reviewer-tags-2025-jx-af-a-new.json",
            "reviewer-tags-2025-jx-af-b.json",
        ),
        (
            "2025-nanjing-af-recheck",
            "reviewer-tags-2025-nanjing-af-a.json",
            "reviewer-tags-2025-nanjing-af-b.json",
        ),
    ),
}

OUTPUT_SPECS = {
    "links": (
        "reviewer-links-final-consensus-1.json",
        "reviewer-links-final-consensus-2.json",
    ),
    "tags": (
        "reviewer-tags-final-consensus-1.json",
        "reviewer-tags-final-consensus-2.json",
    ),
}


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def row_key(record: Mapping[str, Any]) -> str | None:
    # Prefer explicit contestKey+alias when present.  A few reports include a
    # provenance suffix in ``key`` (for example qoj:17466:A:gdcpc23rd), while
    # their explicit fields still identify the target row unambiguously.
    explicit_contest = str(record.get("contestKey") or "").strip().replace("__", "/")
    explicit_alias = str(record.get("alias") or "").strip()
    if explicit_contest and explicit_alias:
        explicit_contest = CONTEST_KEY_ALIASES.get(explicit_contest, explicit_contest)
        return f"{explicit_contest}:{explicit_alias}"
    raw = record.get("key") or record.get("canonicalKey") or record.get("problemKey")
    if raw:
        value = str(raw).strip().replace("__", "/")
        contest, sep, alias = value.rpartition(":")
        if sep:
            contest = CONTEST_KEY_ALIASES.get(contest, contest)
            return f"{contest}:{alias}"
        return value
    contest = str(record.get("contestKey") or "").strip().replace("__", "/")
    contest = CONTEST_KEY_ALIASES.get(contest, contest)
    alias = str(record.get("alias") or "").strip()
    return f"{contest}:{alias}" if contest and alias else None


def report_records(path: Path) -> dict[str, dict[str, Any]]:
    payload = read_json(path, {})
    if not isinstance(payload, Mapping):
        return {}
    records = payload.get("records")
    if not isinstance(records, list):
        records = payload.get("checkedRows")
    if not isinstance(records, list):
        records = payload.get("candidates")
    if not isinstance(records, (list, Mapping)):
        records = payload.get("problems")
    if not isinstance(records, (list, Mapping)):
        records = payload.get("entries")
    # A few independent reviewers naturally group their rows by problem
    # letter under a top-level ``problems`` object.  Accept that shape at the
    # audit boundary while adding the contest key from the report envelope;
    # the row itself still has to carry its own evidence and status before it
    # can participate in consensus.
    if isinstance(records, Mapping):
        envelope_contest = str(payload.get("contestKey") or "").strip()
        converted: list[dict[str, Any]] = []
        for alias, value in records.items():
            if not isinstance(value, Mapping):
                continue
            item = dict(value)
            item.setdefault("alias", str(alias).strip())
            if envelope_contest:
                item.setdefault("contestKey", envelope_contest)
            converted.append(item)
        records = converted
    result: dict[str, dict[str, Any]] = {}
    for item in records if isinstance(records, list) else []:
        if isinstance(item, Mapping):
            item = dict(item)
            # Reviewer reports use both ``alias`` and the compact ``label``
            # spelling for the A--M column.  Normalize only the envelope
            # metadata here; the actual verdict/evidence remains untouched.
            if not str(item.get("contestKey") or "").strip():
                envelope_contest = str(payload.get("contestKey") or "").strip()
                if envelope_contest:
                    item["contestKey"] = envelope_contest
            if not str(item.get("alias") or "").strip() and item.get("label") is not None:
                item["alias"] = item.get("label")
            # Some independent reports use ``problemKey`` for the column
            # letter while keeping the contest only on the report envelope.
            # Promote that field to the canonical alias before constructing
            # the row key; otherwise a perfectly valid pair is keyed as just
            # ``A`` and can never meet its inventory row.
            if not str(item.get("alias") or "").strip() and item.get("problemKey") is not None:
                item["alias"] = item.get("problemKey")
            if item.get("labels") is None and item.get("broadLabels") is not None:
                item["labels"] = item.get("broadLabels")
            if not (item.get("evidence") or item.get("sourceEvidence") or item.get("reason")):
                item_evidence = item.get("evidenceUrl") or item.get("source")
                if item_evidence:
                    item["evidence"] = item_evidence
            key = row_key(item)
            if key:
                result[key] = item
    return result


def status(record: Mapping[str, Any] | None) -> str:
    return str((record or {}).get("status") or "UNRESOLVED").upper()


def canonical_url(value: Any) -> str | None:
    # Importing the project's validator keeps this bridge aligned with the
    # exact URL policy used by the finalizer.
    from merge_problem_audit import canonical_problem_url

    return canonical_problem_url(value)


def safe_title(record: Mapping[str, Any] | None) -> str | None:
    from merge_problem_audit import valid_title

    record = record or {}
    raw = record.get("title") or record.get("problemTitle") or record.get("name")
    value = valid_title(raw)
    # A short title such as ``CCPC`` can be a real problem name (the 2024
    # vocational contest has an official problem literally named CCPC).  The
    # general merge validator treats these words as placeholders, so allow
    # them here only when the reviewer marked the row PASS, supplied a direct
    # individual URL, and left source evidence.  Unreviewed production rows
    # continue to use the conservative placeholder rule.
    if value is None and isinstance(raw, str):
        candidate = " ".join(raw.replace("\xa0", " ").split()).strip()
        if (
            candidate
            and candidate.casefold() in {"ccpc", "icpc", "problem", "502 bad gateway", "bad gateway"}
            and status(record) == "PASS"
            and canonical_url(record.get("problemUrl") or record.get("url") or record.get("source"))
            and (record.get("evidence") or record.get("sourceEvidence") or record.get("source"))
        ):
            value = candidate
    if not value:
        return None
    alias = str(record.get("alias") or "").strip()
    if alias and value.strip() == alias:
        return None
    return value


def normalized_labels(value: Any) -> dict[str, float]:
    from finalize_problem_audit import normalized_labels as normalize

    # Some independent reviewers use a list of coarse-axis keys instead of a
    # weight map. Treat that representation as equal weights, then run the
    # same canonical validation as production.
    if isinstance(value, (list, tuple, set)):
        keys = [str(item).strip() for item in value if str(item).strip()]
        if not keys:
            return {}
        value = {key: 1.0 for key in keys}
    return normalize(value)


def tag_value(record: Mapping[str, Any] | None) -> Any:
    record = record or {}
    return record.get("labels") if record.get("labels") is not None else record.get("coarseTags")


def normalized_details(value: Any) -> list[str]:
    from finalize_problem_audit import normalized_details as normalize

    # Detail tags are a set semantically; reviewer ordering must not create a
    # false disagreement.  Sorting also makes the emitted pair deterministic.
    return sorted(normalize(value))


def strict_normalized_details(value: Any) -> tuple[bool, list[str]]:
    """Return validity separately so corrupt tags cannot become an empty set."""

    from finalize_problem_audit import strict_normalized_details as normalize

    valid, details = normalize(value)
    return valid, sorted(details)


def generated_rounds(field: str) -> list[tuple[str, str, str]]:
    """Read batch-registered reviewer pairs for ``field``.

    Each entry names two *distinct* report files that were produced by two
    independent reviewers for the same contest shard.  Only entries whose two
    files both exist are returned, so a half-finished batch can never create a
    synthetic consensus on its own.
    """

    payload = read_json(AUDIT_ROOT / GENERATED_ROUNDS_PATH, {})
    entries = payload.get(field) if isinstance(payload, Mapping) else None
    result: list[tuple[str, str, str]] = []
    for item in entries if isinstance(entries, list) else []:
        if not isinstance(item, Mapping):
            continue
        label = str(item.get("label") or "").strip()
        left = str(item.get("left") or "").strip()
        right = str(item.get("right") or "").strip()
        if not label or not left or not right or left == right:
            continue
        if not (AUDIT_ROOT / left).is_file() or not (AUDIT_ROOT / right).is_file():
            continue
        result.append((label, left, right))
    return result


def load_root_adjudications(field: str) -> dict[str, dict[str, Any]]:
    """Read explicit root decisions for rows where reviewer values diverge.

    Adjudications are deliberately opt-in and narrowly validated.  They are
    a documented escape hatch for the user's stated rule that the root agent
    may decide after an independent review disagreement; malformed entries do
    not get a chance to alter the generated pair.
    """

    payload = read_json(ROOT_ADJUDICATION_PATH, {})
    if not isinstance(payload, Mapping):
        return {}
    section = payload.get(field)
    result: dict[str, dict[str, Any]] = {}
    if isinstance(section, Mapping):
        iterable = []
        for raw_key, value in section.items():
            if isinstance(value, Mapping):
                item = dict(value)
                item.setdefault("key", raw_key)
                iterable.append(item)
    elif isinstance(section, list):
        iterable = [item for item in section if isinstance(item, Mapping)]
    else:
        iterable = []
    for item in iterable:
        key = row_key(item)
        if key:
            result[key] = dict(item)
    return result


def validate_root_adjudication(field: str, item: Mapping[str, Any] | None) -> tuple[bool, Any, str]:
    """Validate and return the selected root value for one row."""

    item = item or {}
    decision = str(item.get("decision") or "").strip().lower()
    if decision not in {"approve", "approved", "pass"}:
        return False, None, "root adjudication is not an approval"
    evidence = item.get("evidence") or item.get("reason")
    if not evidence or (isinstance(evidence, str) and not evidence.strip()):
        return False, None, "root adjudication has no evidence"
    reviewers = item.get("reviewers")
    if (not isinstance(reviewers, list)
            or len({str(name).strip() for name in reviewers if str(name).strip()}) < 2):
        return False, None, "root adjudication must name two reviewer sources"
    if field == "links":
        url = canonical_url(item.get("problemUrl") or item.get("url"))
        title = safe_title(item)
        if not url or not title:
            return False, None, "root link adjudication has no direct URL and title"
        return True, (url, title), "explicit root link adjudication"
    labels = normalized_labels(item.get("labels"))
    details_ok, details = strict_normalized_details(item.get("detailTags"))
    if not details_ok:
        return False, None, "root tag adjudication has invalid canonical detail tags"
    if not labels:
        return False, None, "root tag adjudication has invalid canonical labels"
    return True, (labels, details), "explicit root tag adjudication"


def validate_root_rejection(item: Mapping[str, Any] | None) -> tuple[bool, str]:
    """Validate a documented root decision that blocks publication."""

    item = item or {}
    decision = str(item.get("decision") or "").strip().lower()
    if decision not in {"reject", "rejected", "fail"}:
        return False, "root decision is not a rejection"
    evidence = item.get("evidence") or item.get("reason")
    if not evidence or (isinstance(evidence, str) and not evidence.strip()):
        return False, "root rejection has no evidence"
    reviewers = item.get("reviewers")
    if (not isinstance(reviewers, list)
            or len({str(name).strip() for name in reviewers if str(name).strip()}) < 2):
        return False, "root rejection must name two reviewer sources"
    disposition = str(item.get("disposition") or "").strip().lower()
    if disposition and disposition != "withdrawn":
        return False, "unsupported root rejection disposition"
    return True, "explicit root rejection"


def adjudication_source_records(
    key: str, item: Mapping[str, Any],
    reports: dict[str, dict[str, dict[str, Any]]],
) -> tuple[list[dict[str, Any]], str]:
    """Require two actual per-problem reviews before adjudicating disagreement.

    An unavailable reviewer is not a negative review. Loading explicitly named
    reports also permits a real independent review outside the ordinary pairs.
    """
    names = item.get("reviewerFiles")
    if (not isinstance(names, list) or len(names) < 2
            or any(not isinstance(name, str) or not name.strip() for name in names[:2])):
        return [], "root adjudication needs two original reviewer files"
    paths = [(AUDIT_ROOT / name).resolve() for name in names[:2]]
    if paths[0] == paths[1]:
        return [], "root adjudication needs two distinct original reviewer files"
    records = []
    for name, path in zip(names[:2], paths):
        if not path.is_file():
            return [], f"root reviewer file is missing: {name}"
        if name not in reports:
            reports[name] = report_records(path)
        record = reports[name].get(key)
        if not record:
            return [], f"root reviewer has no record for this problem: {name}"
        evidence = record.get("evidence") or record.get("sourceEvidence") or record.get("reason")
        if not evidence or not str(evidence).strip():
            return [], f"root reviewer record has no evidence: {name}"
        records.append(dict(record))
    return records, "two original reviewer records found"


def link_consensus(left: Mapping[str, Any] | None, right: Mapping[str, Any] | None) -> tuple[bool, str | None, str | None, str]:
    if status(left) != "PASS" or status(right) != "PASS":
        return False, None, None, "both reports must say PASS"
    url_left = canonical_url((left or {}).get("problemUrl") or (left or {}).get("url") or (left or {}).get("source"))
    url_right = canonical_url((right or {}).get("problemUrl") or (right or {}).get("url") or (right or {}).get("source"))
    title_left, title_right = safe_title(left), safe_title(right)
    if not url_left or not url_right:
        return False, None, None, "missing direct individual URL"
    if url_left != url_right:
        return False, None, None, "different URLs"
    if not title_left or not title_right or title_left != title_right:
        return False, None, None, "different or unusable titles"
    return True, url_left, title_left, "two independent round-2 reports agree"


def tag_consensus(left: Mapping[str, Any] | None, right: Mapping[str, Any] | None) -> tuple[bool, dict[str, float], list[str], str]:
    if status(left) != "PASS" or status(right) != "PASS":
        return False, {}, [], "both reports must say PASS"
    labels_left, labels_right = normalized_labels(tag_value(left)), normalized_labels(tag_value(right))
    details_left_ok, details_left = strict_normalized_details((left or {}).get("detailTags"))
    details_right_ok, details_right = strict_normalized_details((right or {}).get("detailTags"))
    # A problem whose official solution names no registered technique is still
    # publishable: both reviewers agree on the coarse axes and both explicitly
    # report an empty fine-grained tag list.  Any other mismatch falls through
    # to the checks below.
    if details_left_ok and details_right_ok and labels_left and labels_left == labels_right and not details_left and not details_right:
        return True, labels_left, [], "two independent round-2 reports agree (no fine-grained technique named)"
    if not details_left_ok or not details_right_ok or not labels_left or not labels_right or not details_left or not details_right:
        return False, {}, [], "missing complete canonical labels"
    if labels_left != labels_right:
        return False, {}, [], "different coarse labels"
    if details_left != details_right:
        return False, {}, [], "different detail labels"
    return True, labels_left, details_left, "two independent round-2 reports agree"


def make_unresolved(key: str, left: Mapping[str, Any] | None, right: Mapping[str, Any] | None) -> dict[str, Any]:
    contest, _, alias = key.rpartition(":")
    return {
        "key": key,
        "contestKey": contest,
        "alias": alias,
        "status": "UNRESOLVED",
        "evidence": "round-2 pair incomplete or unresolved",
    }


def target_problem_keys() -> set[str]:
    """Return the canonical rows in the published 2022--2026 inventory.

    Reviewer artifacts can contain an extra row (for example a platform's
    preliminary contest has an M problem while the target contest has only
    A--L).  Restricting the bridge to the inventory prevents such artifacts
    from changing audit totals or creating phantom public rows.
    """

    result: set[str] = set()
    root = ROOT / "data" / "problem"
    for path in root.glob("*/*.json"):
        payload = read_json(path, {})
        rows = payload.get("problems") if isinstance(payload, Mapping) else None
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            contest = str(row.get("contestKey") or "").strip().replace("__", "/")
            alias = str(row.get("alias") or "").strip()
            if contest and alias:
                result.add(f"{contest}:{alias}")
    return result


def build_field(field: str) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    base_paths = [AUDIT_ROOT / name for name, _ in BASE_SPECS[field]]
    base_maps = [report_records(path) for path in base_paths]
    report_maps_by_name: dict[str, dict[str, dict[str, Any]]] = {
        path.name: records for path, records in zip(base_paths, base_maps)
    }
    # Start with every key known to either base report.  New reports can add a
    # key only when both members of their pair exist and agree.
    all_keys = set().union(*(m.keys() for m in base_maps))
    round_pairs: list[tuple[str, dict[str, dict[str, Any]], dict[str, dict[str, Any]]]] = []
    skipped: list[str] = []
    for label, left_name, right_name in list(ROUND_SPECS[field]) + generated_rounds(field):
        left_path, right_path = AUDIT_ROOT / left_name, AUDIT_ROOT / right_name
        if not left_path.exists() or not right_path.exists():
            skipped.append(label)
            continue
        left_map, right_map = report_records(left_path), report_records(right_path)
        report_maps_by_name[left_name] = left_map
        report_maps_by_name[right_name] = right_map
        round_pairs.append((label, left_map, right_map))
        all_keys.update(left_map)
        all_keys.update(right_map)

    # Never let a reviewer-only key escape into the synthetic pair.
    inventory_keys = target_problem_keys()
    if inventory_keys:
        all_keys.intersection_update(inventory_keys)

    # Manual decisions are only allowed to address rows already present in
    # the target baseline.  This prevents a typo in an adjudication key from
    # creating an extra public row.
    root_adjudications = {
        key: value
        for key, value in load_root_adjudications(field).items()
        if key in all_keys
    }

    # selected[key] = (left record, right record, provenance label), where the
    # selected pair is either a new exact consensus or the original pair.
    selected: dict[str, tuple[dict[str, Any], dict[str, Any], str]] = {}
    conflicts: list[dict[str, Any]] = []
    counters = Counter()
    for key in sorted(all_keys):
        candidates: list[tuple[str, dict[str, Any], dict[str, Any], Any]] = []
        for label, left_map, right_map in round_pairs:
            left, right = left_map.get(key), right_map.get(key)
            if field == "links":
                ok, value, title, reason = link_consensus(left, right)
                payload = (value, title) if ok else None
            else:
                ok, labels, details, reason = tag_consensus(left, right)
                payload = (labels, details) if ok else None
            if ok:
                candidates.append((label, left or {}, right or {}, payload))

        # An explicit root decision takes precedence over an unresolved or
        # conflicting pair.  We still copy the named reviewer records so the
        # final review object retains the original evidence and disagreement.
        manual = root_adjudications.get(key)
        if manual is not None:
            rejection_ok, rejection_reason = validate_root_rejection(manual)
            if rejection_ok:
                sources, source_reason = adjudication_source_records(
                    key, manual, report_maps_by_name
                )
                if not sources:
                    rejection_ok, rejection_reason = False, source_reason
            if rejection_ok:
                left, right = sources
                left["originalReview"] = dict(left)
                right["originalReview"] = dict(right)
                root_meta = {
                    "decision": "reject",
                    "disposition": manual.get("disposition"),
                    "reason": str(manual.get("reason") or rejection_reason),
                    "evidence": manual.get("evidence"),
                    "reviewers": list(manual.get("reviewers") or []),
                    "reviewerFiles": [
                        str(name) for name in manual["reviewerFiles"][:2]
                    ],
                    "source": manual.get("source"),
                }
                left["rootRejection"] = root_meta
                right["rootRejection"] = root_meta
                selected[key] = (
                    left,
                    right,
                    f"root-reject:{manual.get('id') or field}",
                )
                counters["rootRejection"] += 1
                continue
            manual_ok, manual_payload, manual_reason = validate_root_adjudication(field, manual)
            if manual_ok:
                sources, source_reason = adjudication_source_records(key, manual, report_maps_by_name)
                if not sources:
                    manual_ok, manual_reason = False, source_reason
            if manual_ok:
                reviewer_files = manual["reviewerFiles"]
                left, right = sources
                # The compatibility fields below carry the root's selected
                # value. Keep a complete snapshot of each original opinion.
                left["originalReview"] = dict(left)
                right["originalReview"] = dict(right)
                if field == "links":
                    url, title = manual_payload
                    left["problemUrl"] = url; right["problemUrl"] = url
                    left["title"] = title; right["title"] = title
                else:
                    labels, details = manual_payload
                    left["labels"] = labels; right["labels"] = labels
                    left["detailTags"] = details; right["detailTags"] = details
                root_meta = {
                    "decision": "approve",
                    "reason": str(manual.get("reason") or manual_reason),
                    "evidence": manual.get("evidence"),
                    "reviewers": list(manual.get("reviewers") or []),
                    "reviewerFiles": [str(name) for name in reviewer_files[:2]],
                    "source": manual.get("source"),
                }
                left["rootAdjudication"] = root_meta
                right["rootAdjudication"] = root_meta
                selected[key] = (
                    left,
                    right,
                    f"root:{manual.get('id') or field}",
                )
                counters["rootAdjudication"] += 1
                # Keep a machine-readable trace when the manual choice
                # supersedes an otherwise valid round-2 candidate.
                if candidates:
                    if any(item[3] != manual_payload for item in candidates):
                        counters["conflict"] += 1
                        conflicts.append(
                            {
                                "key": key,
                                "field": field,
                                "type": "root-adjudication-overrode-round2",
                                "manual": manual_payload,
                                "candidates": [
                                    {"round": item[0], "value": item[3]}
                                    for item in candidates
                                ],
                            }
                        )
                continue
            conflicts.append(
                {
                    "key": key,
                    "field": field,
                    "type": "invalid-root-adjudication",
                    "reason": manual_reason,
                }
            )
        if len(candidates) > 1:
            first_payload = candidates[0][3]
            if any(item[3] != first_payload for item in candidates[1:]):
                conflicts.append(
                    {
                        "key": key,
                        "field": field,
                        "candidates": [
                            {"round": item[0], "value": item[3]} for item in candidates
                        ],
                    }
                )
                counters["conflict"] += 1
                # Keep the old pair; the root agent must make the final choice
                # after inspecting the evidence rather than guessing here.
                candidates = []
        if candidates:
            label, left, right, _payload = candidates[0]
            selected[key] = (dict(left), dict(right), f"round2:{label}")
            counters["newConsensus"] += 1
        else:
            left = dict(base_maps[0].get(key) or make_unresolved(key, None, None))
            right = dict(base_maps[1].get(key) or make_unresolved(key, None, None))
            selected[key] = (left, right, "baseline")
            counters["baseline"] += 1

    generated = datetime.now(timezone.utc).isoformat()
    output_records: list[dict[str, Any]] = []
    first_records: list[dict[str, Any]] = []
    second_records: list[dict[str, Any]] = []
    for key, (left, right, provenance) in selected.items():
        left = dict(left); right = dict(right)
        left["key"] = key; right["key"] = key
        # Emit the canonical target identity in both synthetic reports.  This
        # keeps audit metadata readable even when a source reviewer used a
        # platform-specific contest slug.
        left["contestKey"] = key.rsplit(":", 1)[0]; right["contestKey"] = key.rsplit(":", 1)[0]
        left["alias"] = key.rsplit(":", 1)[-1]; right["alias"] = key.rsplit(":", 1)[-1]
        # Emit one canonical tag representation even when a source reviewer
        # used ``coarseTags`` (a list) instead of weighted ``labels``.  This
        # keeps the synthetic pair consumable by the production finalizer and
        # leaves baseline rows untouched.
        if field == "tags" and (provenance.startswith("round2:") or provenance.startswith("root:")):
            labels = normalized_labels(tag_value(left))
            details = normalized_details(left.get("detailTags"))
            if labels and details:
                left["labels"] = labels; right["labels"] = labels
                left["detailTags"] = details; right["detailTags"] = details
        left["consensusProvenance"] = provenance
        right["consensusProvenance"] = provenance
        first_records.append(left); second_records.append(right)
        output_records.append({"key": key, "provenance": provenance})

    names = OUTPUT_SPECS[field]
    common = {
        "generated": generated,
        "reviewer": f"{field}-reviewer-round2-consensus",
        "independence": "pair-preserving merge; each ordinary new value requires two matching PASS reports; explicit root approvals or rejections retain both source reports and rationale",
        "scope": "all target rows represented by baseline or available round-2 reports",
    }
    first_payload = dict(common)
    first_payload["reviewer"] = f"{field}-reviewer-1-consensus"
    first_payload["summary"] = {"checked": len(first_records), "newConsensus": counters["newConsensus"], "rootAdjudication": counters["rootAdjudication"], "rootRejection": counters["rootRejection"], "baseline": counters["baseline"], "conflict": counters["conflict"]}
    first_payload["records"] = first_records
    second_payload = dict(common)
    second_payload["reviewer"] = f"{field}-reviewer-2-consensus"
    second_payload["summary"] = first_payload["summary"]
    second_payload["records"] = second_records
    return first_payload, second_payload, conflicts, {
        "field": field,
        "checked": len(output_records),
        "newConsensus": counters["newConsensus"],
        "rootAdjudication": counters["rootAdjudication"],
        "rootRejection": counters["rootRejection"],
        "baseline": counters["baseline"],
        "conflict": counters["conflict"],
        "skippedRounds": skipped,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="compute counts without writing reports")
    args = parser.parse_args()
    all_conflicts: list[dict[str, Any]] = []
    summaries: dict[str, Any] = {}
    for field in ("links", "tags"):
        first, second, conflicts, summary = build_field(field)
        summaries[field] = summary
        all_conflicts.extend(conflicts)
        if not args.dry_run:
            first_path, second_path = (AUDIT_ROOT / name for name in OUTPUT_SPECS[field])
            write_json(first_path, first)
            write_json(second_path, second)
    if not args.dry_run:
        write_json(AUDIT_ROOT / "round2-consensus-conflicts.json", {"generated": datetime.now(timezone.utc).isoformat(), "conflicts": all_conflicts})
    print(json.dumps({"fields": summaries, "conflicts": len(all_conflicts)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
