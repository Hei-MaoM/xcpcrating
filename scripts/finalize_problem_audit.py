#!/usr/bin/env python3
"""Apply the two-pass metadata review gate to the generated problem bundle.

``merge_problem_audit.py`` intentionally produces a rich candidate bundle.
This script is the publication gate: a public link or algorithm tag is kept
only when two independent reviewer reports agree on the exact value.  A
candidate that is not yet agreed is retained in the review record and removed
from the user-facing field so an attractive but incorrect value cannot leak
into the site.

The command is deterministic and can be rerun after a reviewer refreshes a
report.  Use ``--dry-run`` to inspect the decision counts without changing the
bundle.
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from xcpc_rating.problem_tags import normalize_detail_tags  # noqa: E402
from xcpc_rating.problem_types import normalize_label_weights, PROBLEM_TYPE_LABELS  # noqa: E402

from merge_problem_audit import (  # noqa: E402
    canonical_for_url,
    canonical_problem_url,
    contest_slug,
    valid_title,
    write_json,
)


DATA_ROOT = ROOT / "data" / "problem"
MANIFEST_PATH = ROOT / "data" / "problem-types" / "2023-present-all-qoj-v2.json"
CATALOG_PATH = ROOT / "data" / "problem-catalog.json"
AUDIT_ROOT = ROOT / "work" / "problem-audit"
SUMMARY_PATH = AUDIT_ROOT / "final-review-summary.json"
BACKUP_ROOT = AUDIT_ROOT / "pre-consensus"
WEB_PROGRESS_PATH = ROOT / "web" / "public" / "data" / "problem-audit-progress.json"


# These values are source placeholders, not problem names.  They appeared in
# a few mirror rows and must never be published as a title.
GENERIC_TITLES = frozenset(
    {
        "ccpc",
        "icpc",
        "problem",
        "题目",
        "未命名题目",
        "unknown",
        "null",
    }
)


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def clean_key(value: Any) -> str:
    return str(value or "").strip().replace("__", "/")


def row_key(record: Mapping[str, Any]) -> str | None:
    # Reviewer artifacts may carry a platform-specific or provenance-heavy
    # ``key``.  Explicit contestKey+alias is the authoritative target identity
    # when both fields are present.
    explicit_contest = clean_key(record.get("contestKey"))
    explicit_alias = str(record.get("alias") or "").strip()
    if explicit_contest and explicit_alias:
        return f"{explicit_contest}:{explicit_alias}"
    raw = record.get("key") or record.get("canonicalKey") or record.get("problemKey")
    if raw:
        return clean_key(raw)
    contest = clean_key(record.get("contestKey"))
    alias = str(record.get("alias") or "").strip()
    if contest and alias:
        return f"{contest}:{alias}"
    return None


def report_records(path: Path) -> dict[str, dict[str, Any]]:
    """Read either reviewer report shape used by the audit agents."""

    payload = read_json(path, {})
    if not isinstance(payload, Mapping):
        return {}
    records: Any = payload.get("records")
    if not isinstance(records, list):
        records = payload.get("checkedRows")
    if not isinstance(records, list):
        records = payload.get("candidates")
    result: dict[str, dict[str, Any]] = {}
    for item in records:
        if not isinstance(item, Mapping):
            continue
        key = row_key(item)
        if key:
            result[key] = dict(item)
    return result


def safe_title(
    value: Any,
    alias: str,
    *,
    verified_url: Any = None,
    status: Any = None,
    evidence: Any = None,
) -> str | None:
    title = valid_title(value)
    verified_generic = False
    # ``CCPC``/``ICPC`` can be genuine short problem names.  The shared
    # source validator conservatively filters those words because they often
    # appear as contest placeholders.  A reviewed row may retain one only
    # when both the review status and a direct URL/evidence prove it is a
    # statement title.  Calls without review context keep the old filter.
    if title is None and isinstance(value, str):
        candidate = " ".join(value.replace("\xa0", " ").split()).strip()
        direct = canonical_problem_url(verified_url)
        if (
            candidate
            and candidate.casefold() in {"ccpc", "icpc", "problem", "502 bad gateway", "bad gateway"}
            and str(status or "").upper() == "PASS"
            and direct
            and evidence
        ):
            title = candidate
            verified_generic = True
    if not title:
        return None
    if title.strip().lower() in GENERIC_TITLES and not verified_generic:
        return None
    if title.strip() == alias.strip():
        return None
    return title


def safe_record_title(record: Mapping[str, Any] | None, alias: str) -> str | None:
    """Validate a reviewer title with the row's direct-source context."""

    record = record or {}
    return safe_title(
        record.get("title"),
        alias,
        verified_url=record.get("problemUrl") or record.get("url") or record.get("source"),
        status=record.get("status"),
        evidence=record.get("evidence") or record.get("sourceEvidence") or record.get("reason"),
    )


def normalized_labels(value: Any) -> dict[str, float]:
    if not isinstance(value, Mapping):
        return {}
    try:
        labels = normalize_label_weights(value)
    except (TypeError, ValueError):
        return {}
    if not labels:
        return {}
    total = sum(float(v) for v in labels.values())
    if not math.isfinite(total) or total <= 0:
        return {}
    # Stable rounding prevents insignificant JSON float noise from looking
    # like a reviewer disagreement.
    return {str(k): round(float(v) / total, 6) for k, v in labels.items()}


def normalized_details(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    try:
        return normalize_detail_tags(value)
    except (TypeError, ValueError):
        return []


def strict_normalized_details(value: Any) -> tuple[bool, list[str]]:
    """Validate a reviewer's fine tags without conflating bad data with none.

    ``normalized_details`` is intentionally forgiving for legacy production
    rows, where an invalid historical value should be treated as unavailable.
    The two-reviewer publication gate needs a stricter distinction: a report
    that supplied unknown/corrupted labels must not be accepted as if it had
    explicitly supplied an empty list.
    """

    if not isinstance(value, list):
        return False, []
    try:
        return True, normalize_detail_tags(value)
    except (TypeError, ValueError):
        return False, []


def same_labels(left: Any, right: Any) -> bool:
    a, b = normalized_labels(left), normalized_labels(right)
    return bool(a) and a == b


def same_details(left: Any, right: Any) -> bool:
    a, b = normalized_details(left), normalized_details(right)
    return bool(a) and a == b


def valid_root_context(root: Mapping[str, Any], first: Mapping[str, Any], second: Mapping[str, Any]) -> bool:
    """Reject hand-written root approvals that lost the original reviews.

    The bridge writes both source snapshots into ``originalReview``. Requiring
    them here keeps this final publication gate safe even when a caller feeds
    it a report that did not pass through the bridge.
    """
    decision = str(root.get("decision") or "").strip().lower()
    evidence = root.get("evidence") or root.get("reason")
    reviewers = root.get("reviewers")
    files = root.get("reviewerFiles")
    if decision not in {"approve", "approved", "pass"} or not evidence or (isinstance(evidence, str) and not evidence.strip()):
        return False
    if (not isinstance(reviewers, list) or len({str(x).strip() for x in reviewers if str(x).strip()}) < 2
            or not isinstance(files, list) or len(files) < 2
            or len({str(x).strip() for x in files[:2] if str(x).strip()}) < 2):
        return False
    for record in (first, second):
        original = record.get("originalReview")
        if not isinstance(original, Mapping):
            return False
        source_evidence = original.get("evidence") or original.get("sourceEvidence") or original.get("reason")
        if not source_evidence or (isinstance(source_evidence, str) and not source_evidence.strip()):
            return False
    return True


def valid_root_rejection_context(
    root: Mapping[str, Any], first: Mapping[str, Any], second: Mapping[str, Any]
) -> bool:
    """Require the same review trail for a root rejection as for an approval."""

    decision = str(root.get("decision") or "").strip().lower()
    if decision not in {"reject", "rejected", "fail"}:
        return False
    approval_shaped = dict(root)
    approval_shaped["decision"] = "approve"
    return valid_root_context(approval_shaped, first, second)


def reviewer_summary(name: str, record: Mapping[str, Any] | None, *, field: str) -> dict[str, Any]:
    record = record or {}
    evidence = record.get("evidence") or record.get("sourceEvidence") or record.get("reason")
    if isinstance(evidence, list):
        evidence = "; ".join(str(x) for x in evidence if x)
    result: dict[str, Any] = {
        "name": name,
        "status": str(record.get("status") or "UNRESOLVED"),
    }
    if evidence:
        result["evidence"] = str(evidence)[:1200]
    if field == "links":
        url = canonical_problem_url(record.get("problemUrl") or record.get("url") or record.get("source"))
        title = safe_record_title(record, str(record.get("alias") or ""))
        if url:
            result["problemUrl"] = url
        if title:
            result["title"] = title
    else:
        labels = normalized_labels(record.get("labels"))
        details = normalized_details(record.get("detailTags"))
        if labels:
            result["labels"] = labels
        if details:
            result["detailTags"] = details
    root_adjudication = record.get("rootAdjudication")
    if isinstance(root_adjudication, Mapping):
        # Preserve the root's rationale alongside the original reviewer
        # result.  This makes an adjudicated disagreement visible in the
        # public audit trail instead of presenting it as a false consensus.
        result["rootAdjudication"] = {
            key: root_adjudication[key]
            for key in ("decision", "reason", "evidence", "reviewers", "reviewerFiles", "source")
            if key in root_adjudication
        }
        original = record.get("originalReview")
        if isinstance(original, Mapping):
            # Summarize once; never recurse through synthetic review history.
            original = dict(original)
            original.pop("rootAdjudication", None)
            original.pop("originalReview", None)
            result["originalReview"] = reviewer_summary(name, original, field=field)
    root_rejection = record.get("rootRejection")
    if isinstance(root_rejection, Mapping):
        result["rootRejection"] = {
            key: root_rejection[key]
            for key in ("decision", "disposition", "reason", "evidence", "reviewers", "reviewerFiles", "source")
            if key in root_rejection
        }
        original = record.get("originalReview")
        if isinstance(original, Mapping) and "originalReview" not in result:
            original = dict(original)
            original.pop("rootRejection", None)
            original.pop("originalReview", None)
            result["originalReview"] = reviewer_summary(name, original, field=field)
    return result


def broad_tags(labels: Mapping[str, float]) -> list[dict[str, Any]]:
    return [
        {
            "key": axis,
            "label": PROBLEM_TYPE_LABELS[axis],
            "weight": round(float(weight), 6),
        }
        for axis, weight in labels.items()
    ]


def iter_problem_documents() -> list[tuple[Path, dict[str, Any]]]:
    result: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted(DATA_ROOT.glob("*/*.json")):
        if path.name == "index.json":
            continue
        payload = read_json(path, {})
        if isinstance(payload, Mapping) and isinstance(payload.get("problems"), list):
            result.append((path, dict(payload)))
    return result


def load_reviewers() -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, Any]]:
    link_specs = (
        ("reviewer-links-final-current-1.json", "links-reviewer-1"),
        ("reviewer-links-final-current-2.json", "links-reviewer-2"),
    )
    tag_specs = (
        ("reviewer-tags-final-current-1.json", "tags-reviewer-1"),
        # The strict report requires direct statement/official tutorial
        # evidence.  The broader balanced report remains an audit candidate,
        # but does not satisfy the publication gate on its own.
        ("reviewer-tags-final-current-2-strict.json", "tags-reviewer-2"),
    )
    # A later audit round may produce partitioned reviewer pairs.  The bridge
    # script materialises them as two complete, pair-preserving reports.  Use
    # those reports when both files are present; otherwise retain the original
    # baseline pair so an interrupted audit can be rerun safely.
    consensus_link_specs = (
        ("reviewer-links-final-consensus-1.json", "links-reviewer-1"),
        ("reviewer-links-final-consensus-2.json", "links-reviewer-2"),
    )
    consensus_tag_specs = (
        ("reviewer-tags-final-consensus-1.json", "tags-reviewer-1"),
        ("reviewer-tags-final-consensus-2.json", "tags-reviewer-2"),
    )
    if all((AUDIT_ROOT / filename).exists() for filename, _name in consensus_link_specs):
        link_specs = consensus_link_specs
    if all((AUDIT_ROOT / filename).exists() for filename, _name in consensus_tag_specs):
        tag_specs = consensus_tag_specs
    links: dict[str, dict[str, Any]] = {}
    tags: dict[str, dict[str, Any]] = {}
    metadata: dict[str, Any] = {"links": [], "tags": []}
    # Keep both reports per key; the nested value is intentionally explicit so
    # a later audit can see which reviewer supplied which decision.
    link_by_key: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    tag_by_key: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for filename, name in link_specs:
        path = AUDIT_ROOT / filename
        records = report_records(path)
        payload = read_json(path, {})
        metadata["links"].append(
            {
                "name": name,
                "file": filename,
                "summary": payload.get("summary", {}) if isinstance(payload, Mapping) else {},
                "rows": len(records),
            }
        )
        for key, record in records.items():
            link_by_key[key][name] = record
    for filename, name in tag_specs:
        path = AUDIT_ROOT / filename
        records = report_records(path)
        payload = read_json(path, {})
        metadata["tags"].append(
            {
                "name": name,
                "file": filename,
                "summary": payload.get("summary", {}) if isinstance(payload, Mapping) else {},
                "rows": len(records),
            }
        )
        for key, record in records.items():
            tag_by_key[key][name] = record
    # Encode the nested maps under sentinel keys.  This avoids a second shape
    # and keeps the caller's loop simple.
    return (
        {key: value for key, value in link_by_key.items()},
        {key: value for key, value in tag_by_key.items()},
        metadata,
    )


def link_decision(key: str, reviewers: Mapping[str, Mapping[str, Any]]) -> tuple[bool, str | None, str | None, str]:
    first = reviewers.get("links-reviewer-1", {})
    second = reviewers.get("links-reviewer-2", {})
    rejection = first.get("rootRejection") if isinstance(first, Mapping) else None
    if not isinstance(rejection, Mapping) and isinstance(second, Mapping):
        rejection = second.get("rootRejection")
    if isinstance(rejection, Mapping) and valid_root_rejection_context(
        rejection, first, second
    ):
        # A rejected link can still have a verified problem title (for
        # example, an officially withdrawn or invalid contest slot).  Carry
        # that title through the decision so finalization does not resurrect
        # a stale title from the pre-audit baseline while clearing the URL.
        rejected_title = safe_record_title(first, key.rsplit(":", 1)[-1])
        if not rejected_title:
            rejected_title = safe_record_title(second, key.rsplit(":", 1)[-1])
        disposition = str(rejection.get("disposition") or "").strip().lower()
        reason = (
            "root withdrawal after independent link review"
            if disposition == "withdrawn"
            else "root rejection after independent link review"
        )
        return False, None, rejected_title, reason
    root = first.get("rootAdjudication") if isinstance(first, Mapping) else None
    if not isinstance(root, Mapping) and isinstance(second, Mapping):
        root = second.get("rootAdjudication")
    if isinstance(root, Mapping) and valid_root_context(root, first, second):
        url = canonical_problem_url(first.get("problemUrl") or second.get("problemUrl"))
        source = first if first.get("title") else second
        # A root decision is itself the documented verification step.  Pass
        # that approval context to the title validator so a genuine short
        # title such as ``ICPC``/``CCPC`` is retained even when the copied
        # reviewer rows are UNRESOLVED or disagree on the host.
        title = safe_title(
            source.get("title"),
            key.rsplit(":", 1)[-1],
            verified_url=url,
            status="PASS",
            evidence=root.get("evidence") or root.get("reason"),
        )
        if url and title:
            return True, url, title, "root adjudication after independent link review disagreement"
    if str(first.get("status")) != "PASS" or str(second.get("status")) != "PASS":
        return False, None, None, "both independent link reviewers must report PASS"
    left_url = canonical_problem_url(first.get("problemUrl") or first.get("url") or first.get("source"))
    right_url = canonical_problem_url(second.get("problemUrl") or second.get("url") or second.get("source"))
    left_title = safe_record_title(first, key.rsplit(":", 1)[-1])
    right_title = safe_record_title(second, key.rsplit(":", 1)[-1])
    if not left_url or not right_url:
        return False, None, None, "reviewer PASS did not contain a direct individual URL"
    if left_url != right_url:
        return False, None, None, "the two link reviewers selected different URLs"
    if not left_title or not right_title or left_title != right_title:
        return False, None, None, "the two link reviewers did not agree on a usable title"
    return True, left_url, left_title, "two-pass link consensus"


def tag_decision(key: str, reviewers: Mapping[str, Mapping[str, Any]]) -> tuple[bool, dict[str, float], list[str], str]:
    first = reviewers.get("tags-reviewer-1", {})
    second = reviewers.get("tags-reviewer-2", {})
    rejection = first.get("rootRejection") if isinstance(first, Mapping) else None
    if not isinstance(rejection, Mapping) and isinstance(second, Mapping):
        rejection = second.get("rootRejection")
    if isinstance(rejection, Mapping) and valid_root_rejection_context(
        rejection, first, second
    ):
        disposition = str(rejection.get("disposition") or "").strip().lower()
        reason = (
            "root withdrawal after independent tag review"
            if disposition == "withdrawn"
            else "root rejection after independent tag review"
        )
        return False, {}, [], reason
    root = first.get("rootAdjudication") if isinstance(first, Mapping) else None
    if not isinstance(root, Mapping) and isinstance(second, Mapping):
        root = second.get("rootAdjudication")
    if isinstance(root, Mapping) and valid_root_context(root, first, second):
        left_labels = normalized_labels(first.get("labels"))
        right_labels = normalized_labels(second.get("labels"))
        left_details_ok, left_details = strict_normalized_details(first.get("detailTags"))
        right_details_ok, right_details = strict_normalized_details(second.get("detailTags"))
        if left_details_ok and right_details_ok and left_labels and left_labels == right_labels and left_details and left_details == right_details:
            return True, left_labels, left_details, "root adjudication after independent tag review disagreement"
    if str(first.get("status")) != "PASS" or str(second.get("status")) != "PASS":
        return False, {}, [], "both independent tag reviewers must report PASS"
    left_labels, right_labels = normalized_labels(first.get("labels")), normalized_labels(second.get("labels"))
    left_details_ok, left_details = strict_normalized_details(first.get("detailTags"))
    right_details_ok, right_details = strict_normalized_details(second.get("detailTags"))
    # Both reviewers may legitimately report "the official solution names no
    # registered technique"; that row is still a verified two-pass consensus as
    # long as the coarse axes agree exactly.
    if left_details_ok and right_details_ok and left_labels and left_labels == right_labels and not left_details and not right_details:
        return True, left_labels, [], "two-pass tag consensus (no fine-grained technique named)"
    if not left_details_ok or not right_details_ok or not left_labels or not right_labels or not left_details or not right_details:
        return False, {}, [], "reviewer PASS did not contain complete canonical labels"
    if left_labels != right_labels:
        return False, {}, [], "the two tag reviewers selected different coarse labels"
    if left_details != right_details:
        return False, {}, [], "the two tag reviewers selected different detail labels"
    return True, left_labels, left_details, "two-pass tag consensus"


def review_status(ok: bool, reason: str) -> str:
    if ok:
        return "approved"
    if reason.startswith("root withdrawal"):
        return "withdrawn"
    return "pending"


def apply(*, dry_run: bool = False, backup: bool = True) -> dict[str, Any]:
    documents = iter_problem_documents()
    link_reviews, tag_reviews, reviewer_metadata = load_reviewers()
    if not documents:
        raise SystemExit("no generated contest documents found under data/problem")

    generated_at = datetime.now(timezone.utc).isoformat()
    counters = Counter()
    contest_counters: dict[str, Counter] = defaultdict(Counter)
    changed = 0
    decisions: list[dict[str, Any]] = []

    for path, payload in documents:
        contest = clean_key(payload.get("contestKey"))
        contest_review = {
            "required": {"tags": 2, "links": 2},
            "tags": {"status": "pending", "reviewers": []},
            "links": {"status": "pending", "reviewers": []},
        }
        next_problems: list[dict[str, Any]] = []
        for raw in payload.get("problems", []):
            if not isinstance(raw, Mapping):
                continue
            problem = dict(raw)
            alias = str(problem.get("alias") or "").strip()
            key = f"{contest}:{alias}"
            link_map = link_reviews.get(key, {})
            tag_map = tag_reviews.get(key, {})
            link_ok, approved_url, approved_title, link_reason = link_decision(key, link_map)
            tag_ok, approved_labels, approved_details, tag_reason = tag_decision(key, tag_map)
            link_status = review_status(link_ok, link_reason)
            tag_status = review_status(tag_ok, tag_reason)

            old_title = safe_title(problem.get("title"), alias)
            old_url = canonical_problem_url(problem.get("problemUrl"))
            old_canonical = problem.get("canonicalId")

            # Keep a safe candidate title visible while its link is pending;
            # generic placeholders and broken encodings are always removed.
            if link_ok:
                problem["problemUrl"] = approved_url
                problem["title"] = approved_title
                # A platform without a canonical id grammar (Pintia sets, school
                # OJs, ...) keeps the event-scoped identity so the row always has
                # a stable, non-empty canonicalId.
                problem["canonicalId"] = (
                    canonical_for_url(approved_url, contest, alias, None) or f"event:{contest}:{alias}"
                )
                problem["sourceKind"] = "two-pass-link-consensus"
                problem["sourceUrl"] = approved_url
                counters["linksApproved"] += 1
                contest_counters[contest]["linksApproved"] += 1
                if link_reason.startswith("root adjudication"):
                    counters["linksRootAdjudicated"] += 1
                    contest_counters[contest]["linksRootAdjudicated"] += 1
            else:
                problem["problemUrl"] = None
                # The manifest schema requires a stable id even while a
                # statement URL is pending.  An event-scoped id is explicit
                # about its provisional nature and cannot collide with a
                # QOJ/Codeforces identity.
                problem["canonicalId"] = f"event:{contest}:{alias}"
                problem["sourceKind"] = (
                    "withdrawn" if link_status == "withdrawn" else "pending-review"
                )
                problem["sourceUrl"] = None
                problem["title"] = approved_title or old_title
                if link_status == "withdrawn":
                    counters["linksWithdrawn"] += 1
                    contest_counters[contest]["linksWithdrawn"] += 1
                else:
                    counters["linksPending"] += 1
                    contest_counters[contest]["linksPending"] += 1

            if tag_ok:
                problem["labels"] = approved_labels
                problem["broadTags"] = broad_tags(approved_labels)
                problem["detailTags"] = approved_details
                problem["status"] = "classified"
                counters["tagsApproved"] += 1
                contest_counters[contest]["tagsApproved"] += 1
                if tag_reason.startswith("root adjudication"):
                    counters["tagsRootAdjudicated"] += 1
                    contest_counters[contest]["tagsRootAdjudicated"] += 1
            else:
                problem["labels"] = {}
                problem["broadTags"] = []
                problem["detailTags"] = []
                problem["status"] = (
                    "withdrawn" if tag_status == "withdrawn" else "unknown"
                )
                problem["confidence"] = 0.2
                if tag_status == "withdrawn":
                    counters["tagsWithdrawn"] += 1
                    contest_counters[contest]["tagsWithdrawn"] += 1
                else:
                    counters["tagsPending"] += 1
                    contest_counters[contest]["tagsPending"] += 1

            if link_ok and tag_ok:
                problem["confidence"] = round(
                    min(
                        float(problem.get("confidence") or 0.99),
                        *[
                            float(item.get("confidence"))
                            for item in list(link_map.values()) + list(tag_map.values())
                            if isinstance(item.get("confidence"), (int, float))
                            and math.isfinite(float(item.get("confidence")))
                        ],
                    ),
                    4,
                ) if any(
                    isinstance(item.get("confidence"), (int, float))
                    and math.isfinite(float(item.get("confidence")))
                    for item in list(link_map.values()) + list(tag_map.values())
                ) else problem.get("confidence", 0.2)

            unresolved: list[str] = []
            if not problem.get("title"):
                unresolved.append("title not confirmed")
            if link_status == "pending":
                unresolved.append(link_reason)
            if tag_status == "pending":
                unresolved.append(tag_reason)
            problem["unresolvedEvidence"] = "; ".join(unresolved) if unresolved else None

            review = {
                "required": {"tags": 2, "links": 2},
                "tags": {
                    "status": tag_status,
                    "decision": (
                        "root-adjudication"
                        if tag_ok and tag_reason.startswith("root adjudication")
                        else "two-pass-consensus" if tag_ok
                        else "withdrawn" if tag_status == "withdrawn"
                        else "pending-review"
                    ),
                    "reviewers": [
                        reviewer_summary(name, tag_map.get(name), field="tags")
                        for name in ("tags-reviewer-1", "tags-reviewer-2")
                    ],
                },
                "links": {
                    "status": link_status,
                    "decision": (
                        "root-adjudication"
                        if link_ok and link_reason.startswith("root adjudication")
                        else "two-pass-consensus" if link_ok
                        else "withdrawn" if link_status == "withdrawn"
                        else "pending-review"
                    ),
                    "reviewers": [
                        reviewer_summary(name, link_map.get(name), field="links")
                        for name in ("links-reviewer-1", "links-reviewer-2")
                    ],
                },
            }
            problem["review"] = review
            if (
                old_title != problem.get("title")
                or old_url != problem.get("problemUrl")
                or old_canonical != problem.get("canonicalId")
                or normalized_labels(raw.get("labels")) != normalized_labels(problem.get("labels"))
                or normalized_details(raw.get("detailTags")) != normalized_details(problem.get("detailTags"))
            ):
                changed += 1
            next_problems.append(problem)

            decisions.append(
                {
                    "key": key,
                    "contestKey": contest,
                    "alias": alias,
                    "links": {"status": link_status, "reason": link_reason},
                    "tags": {"status": tag_status, "reason": tag_reason},
                }
            )

        for field in ("tags", "links"):
            approved = contest_counters[contest][f"{field}Approved"]
            pending = contest_counters[contest][f"{field}Pending"]
            contest_review[field] = {
                "status": "complete" if pending == 0 else "partial",
                "required": 2,
                "approved": approved,
                "pending": pending,
                "rootAdjudicated": contest_counters[contest][f"{field}RootAdjudicated"],
                "withdrawn": contest_counters[contest][f"{field}Withdrawn"],
                "reviewers": [
                    reviewer_metadata[field][0]["name"],
                    reviewer_metadata[field][1]["name"],
                ],
            }
        payload["generatedAt"] = generated_at
        payload["review"] = contest_review
        payload["problems"] = next_problems
        if not dry_run:
            if backup:
                backup_path = BACKUP_ROOT / path.relative_to(DATA_ROOT)
                backup_path.parent.mkdir(parents=True, exist_ok=True)
                if not backup_path.exists():
                    shutil.copy2(path, backup_path)
            write_json(path, payload)

    # Keep the two aggregate stores in sync with the per-contest documents.
    manifest = read_json(MANIFEST_PATH, {})
    catalog = read_json(CATALOG_PATH, {})
    manifest_problems = dict(manifest.get("problems", {})) if isinstance(manifest, Mapping) else {}
    catalog_problems = dict(catalog.get("problems", {})) if isinstance(catalog, Mapping) else {}
    by_key = {dkey: item for _path, payload in documents for item in payload.get("problems", []) if isinstance(item, Mapping) for dkey in [f"{clean_key(item.get('contestKey'))}:{item.get('alias')}" ]}
    # ``documents`` contain the pre-write payload in dry-run mode and the
    # mutated payload in apply mode, so use the decision list for a compact
    # lookup and read the actual files when applying.
    if dry_run:
        # Reconstruct from the in-memory payloads already mutated above.
        pass
    else:
        by_key = {}
        for _path, payload in iter_problem_documents():
            for item in payload.get("problems", []):
                if isinstance(item, Mapping):
                    by_key[f"{clean_key(item.get('contestKey'))}:{item.get('alias')}" ] = item
    for key, item in by_key.items():
        # The manifest schema requires a stable non-empty identity for every
        # row.  A link on a platform without a canonical id grammar (for
        # example a Pintia set or a school OJ) keeps the event-scoped id, so the
        # aggregate store can never carry a null canonicalId.
        contest_part, _, alias_part = key.rpartition(":")
        fallback_canonical = f"event:{contest_part}:{alias_part}"
        canonical_id = item.get("canonicalId") or fallback_canonical
        manifest_problems[key] = {
            "canonicalId": canonical_id,
            "alias": item.get("alias"),
            "labels": item.get("labels") or {},
            "detailTags": item.get("detailTags") or [],
            "confidence": item.get("confidence", 0.2),
            "status": item.get("status", "unknown"),
            "sourceUrl": item.get("sourceUrl"),
            "evidence": item.get("evidence"),
            "unresolvedEvidence": item.get("unresolvedEvidence"),
            "review": item.get("review"),
        }
        catalog_problems[key] = {
            "title": item.get("title"),
            "problemUrl": item.get("problemUrl"),
            "canonicalId": canonical_id,
            "sourceUrl": item.get("sourceUrl"),
            "sourceKind": item.get("sourceKind"),
            "evidence": item.get("evidence"),
            "review": item.get("review"),
        }

    summary = {
        "schemaVersion": "problem-audit-final-v1",
        "generatedAt": generated_at,
        "policy": {
            "links": "publish only exact agreement from two independent PASS reports, or an explicit root adjudication after a documented disagreement",
            "tags": "publish only exact agreement from two independent PASS reports, or an explicit root adjudication after a documented disagreement",
            "titlePlaceholdersRemoved": sorted(GENERIC_TITLES),
        },
        "reports": reviewer_metadata,
        "rows": len(decisions),
        "decisions": dict(counters),
        "contests": len(documents),
        "changedRows": changed,
        "pendingRows": sum(
            1
            for item in decisions
            if item["links"]["status"] not in {"approved", "withdrawn"}
            or item["tags"]["status"] not in {"approved", "withdrawn"}
        ),
        "decisionRows": decisions,
    }

    if not dry_run:
        manifest_out = dict(manifest) if isinstance(manifest, Mapping) else {}
        manifest_out["version"] = "problem-types-audited-v3"
        manifest_out["sourceWindow"] = "2022-2026; two independent reviewer gate"
        manifest_out["problems"] = manifest_problems
        catalog_out = dict(catalog) if isinstance(catalog, Mapping) else {}
        catalog_out["version"] = "problem-catalog-audited-v3"
        catalog_out["problems"] = catalog_problems
        write_json(MANIFEST_PATH, manifest_out)
        write_json(CATALOG_PATH, catalog_out)

        contest_index = []
        progress_contests = []
        for path, payload in iter_problem_documents():
            problems = [item for item in payload.get("problems", []) if isinstance(item, Mapping)]
            approved_links = sum(
                (item.get("review") or {}).get("links", {}).get("status") == "approved"
                for item in problems
            )
            approved_tags = sum(
                (item.get("review") or {}).get("tags", {}).get("status") == "approved"
                for item in problems
            )
            contest_index.append(
                {
                    "year": payload.get("year"),
                    "contestKey": payload.get("contestKey"),
                    "contestSlug": payload.get("contestSlug") or contest_slug(clean_key(payload.get("contestKey"))),
                    "contestName": payload.get("contestName"),
                    "path": str(path.relative_to(ROOT)).replace("\\", "/"),
                    "problemCount": len(problems),
                    "review": payload.get("review"),
                }
            )
            progress_contests.append(
                {
                    "slug": payload.get("contestSlug") or contest_slug(clean_key(payload.get("contestKey"))),
                    "title": payload.get("contestName") or payload.get("contestKey"),
                    "year": str(payload.get("year") or ""),
                    "totalProblems": len(problems),
                    # Link review validates the alias, title and direct URL as
                    # one identity, so title/link progress share this count.
                    "titleChecked": approved_links,
                    "linkChecked": approved_links,
                    "broadTagChecked": approved_tags,
                    "detailTagChecked": approved_tags,
                    "pending": sum(
                        (item.get("review") or {}).get("links", {}).get("status")
                        not in {"approved", "withdrawn"}
                        or (item.get("review") or {}).get("tags", {}).get("status")
                        not in {"approved", "withdrawn"}
                        for item in problems
                    ),
                    "updatedAt": generated_at,
                }
            )
        write_json(
            DATA_ROOT / "index.json",
            {
                "schemaVersion": "problem-metadata-index-v2",
                "generatedAt": generated_at,
                "source": "data/problem; two-pass reviewer gate",
                "review": {
                    "required": {"tags": 2, "links": 2},
                    "approved": {"tags": counters["tagsApproved"], "links": counters["linksApproved"]},
                    "withdrawn": {"tags": counters["tagsWithdrawn"], "links": counters["linksWithdrawn"]},
                    "pending": {"tags": counters["tagsPending"], "links": counters["linksPending"]},
                },
                "contests": sorted(contest_index, key=lambda x: (-int(x.get("year") or 0), str(x.get("contestKey") or ""))),
            },
        )
        write_json(
            WEB_PROGRESS_PATH,
            {
                "version": "problem-audit-progress-v2",
                "generatedAt": generated_at,
                "source": "two independent reviewer consensus",
                "mode": "manual",
                "contests": sorted(
                    progress_contests,
                    key=lambda x: (-int(x.get("year") or 0), str(x.get("title") or "")),
                ),
            },
        )
        write_json(SUMMARY_PATH, summary)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="show decisions without changing production files")
    parser.add_argument("--no-backup", action="store_true", help="do not create the one-time pre-consensus backup")
    args = parser.parse_args(argv)
    summary = apply(dry_run=args.dry_run, backup=not args.no_backup)
    print(json.dumps({k: v for k, v in summary.items() if k not in {"decisionRows"}}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
