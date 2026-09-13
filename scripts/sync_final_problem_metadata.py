#!/usr/bin/env python3
"""Synchronise the reviewed ``data/problem`` fields into the web export.

The rating exporter intentionally starts from raw SRK rows.  This small
post-export step copies only the audited identity/tag fields into both public
problem views, so a pending review cannot be reintroduced by a raw contest
fallback.  It is safe to rerun after every export.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
PROBLEM_ROOT = ROOT / "data" / "problem"
WEB_ROOT = ROOT / "web" / "public" / "data"


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def key(contest: Any, alias: Any) -> str:
    return f"{str(contest or '').replace('__', '/')}:{str(alias or '').strip()}"


def load_final_rows() -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for path in sorted(PROBLEM_ROOT.glob("*/*.json")):
        if path.name == "index.json":
            continue
        payload = read_json(path, {})
        if not isinstance(payload, Mapping):
            continue
        contest = payload.get("contestKey")
        for item in payload.get("problems", []) if isinstance(payload.get("problems"), list) else []:
            if isinstance(item, Mapping):
                result[key(contest, item.get("alias"))] = dict(item)
    return result


def reviewed_fields(item: Mapping[str, Any]) -> dict[str, Any]:
    labels = item.get("labels") if isinstance(item.get("labels"), Mapping) else {}
    ordered = sorted(labels, key=lambda axis: (-float(labels[axis]), str(axis)))
    broad = item.get("broadTags") if isinstance(item.get("broadTags"), list) else []
    return {
        "title": item.get("title") or None,
        "problemUrl": item.get("problemUrl") or None,
        "canonicalId": item.get("canonicalId") or None,
        "typeKeys": ordered if item.get("status") == "classified" else [],
        "typeLabels": [str(entry.get("label")) for entry in broad if isinstance(entry, Mapping) and entry.get("label")]
        if item.get("status") == "classified" else [],
        "detailTags": list(item.get("detailTags")) if item.get("status") == "classified" and isinstance(item.get("detailTags"), list) else [],
        "status": item.get("status") or "unknown",
        "confidence": item.get("confidence", 0.2),
    }


def apply(*, dry_run: bool = False) -> dict[str, int]:
    final = load_final_rows()
    if not final:
        raise SystemExit("no final problem rows found")
    changed_flat = 0
    changed_contests = 0

    index_path = WEB_ROOT / "problems-index.json"
    index = read_json(index_path, [])
    if isinstance(index, list):
        next_rows = []
        for raw in index:
            if not isinstance(raw, Mapping):
                next_rows.append(raw)
                continue
            row = dict(raw)
            match = final.get(key(str(row.get("contestSlug") or "").replace("__", "/"), row.get("alias")))
            if match:
                fields = reviewed_fields(match)
                for field, value in fields.items():
                    if row.get(field) != value:
                        changed_flat += 1
                    row[field] = value
            next_rows.append(row)
        if not dry_run:
            write_json(index_path, next_rows)

    for path in sorted((WEB_ROOT / "contests").glob("*.json")):
        payload = read_json(path, {})
        if not isinstance(payload, Mapping) or not isinstance(payload.get("problems"), list):
            continue
        contest = str(payload.get("id") or path.stem).replace("__", "/")
        doc = dict(payload)
        problems = []
        doc_changed = False
        for raw in payload.get("problems", []):
            if not isinstance(raw, Mapping):
                problems.append(raw)
                continue
            row = dict(raw)
            match = final.get(key(contest, row.get("alias")))
            if match:
                fields = reviewed_fields(match)
                for field, value in fields.items():
                    if row.get(field) != value:
                        doc_changed = True
                    row[field] = value
            problems.append(row)
        if doc_changed:
            changed_contests += 1
            doc["problems"] = problems
            if not dry_run:
                write_json(path, doc)

    return {
        "finalRows": len(final),
        "changedFlatFields": changed_flat,
        "changedContestDocuments": changed_contests,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(json.dumps(apply(dry_run=args.dry_run), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
