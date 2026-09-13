#!/usr/bin/env python3
"""Create a conservative, reviewable mapping from target contests to QOJ ids.

QOJ's public problem index is searched through both the original year crawl and
the expanded contest-name crawl.  A mapping is emitted only when the target
contest has the same number of aliases as the QOJ contest tag.  This keeps
partial warm-up sets and similarly named contests out of the production merge.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
INDEX_PATH = ROOT / "web" / "public" / "data" / "problems-index.json"
AUDIT_ROOT = ROOT / "work" / "problem-audit"
TARGET_CONTESTS_PATH = AUDIT_ROOT / "target-contests-full.tsv"
OLD_QOJ_PATH = AUDIT_ROOT / "qoj-problem-index-2022-2026.json"
EXPANDED_QOJ_PATH = AUDIT_ROOT / "qoj-problem-index-expanded.json"
INDEPENDENT_PATH = AUDIT_ROOT / "qoj-assignments-independent-v2.json"
OUT_PATH = AUDIT_ROOT / "qoj-assignments-final.json"


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def aliases_sort(values: list[str]) -> list[str]:
    def key(value: str) -> tuple[int, str]:
        m = re.fullmatch(r"([A-Za-z])(\d*)", value)
        return (ord(m.group(1).upper()) - 65, m.group(2)) if m else (999, value)

    return sorted(set(values), key=key)


def target_contests() -> tuple[dict[str, list[str]], dict[str, dict[str, Any]]]:
    payload = read_json(INDEX_PATH, [])
    allowed: set[str] = set()
    if TARGET_CONTESTS_PATH.exists():
        raw = TARGET_CONTESTS_PATH.read_bytes()
        text = ""
        for encoding in ("utf-8", "gb18030"):
            try:
                text = raw.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        for line in text.splitlines():
            parts = line.split("\t")
            if len(parts) >= 3 and parts[2].strip():
                allowed.add(parts[2].strip().replace("__", "/"))
    aliases: dict[str, list[str]] = defaultdict(list)
    first: dict[str, dict[str, Any]] = {}
    for row in payload if isinstance(payload, list) else []:
        if not isinstance(row, Mapping):
            continue
        try:
            year = int(str(row.get("startAt") or "")[:4])
        except ValueError:
            continue
        if year not in {2022, 2023, 2024, 2025, 2026}:
            continue
        contest = str(row.get("contestSlug") or "").replace("__", "/")
        alias = str(row.get("alias") or "")
        if not contest or not alias:
            continue
        if allowed and contest not in allowed:
            continue
        aliases[contest].append(alias)
        first.setdefault(contest, {"year": year, "contestTitle": row.get("contestTitle")})
    return {key: aliases_sort(value) for key, value in aliases.items()}, first


def qoj_problem_union() -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for path in (OLD_QOJ_PATH, EXPANDED_QOJ_PATH):
        payload = read_json(path, {})
        problems = payload.get("problems", {}) if isinstance(payload, Mapping) else {}
        if not isinstance(problems, Mapping):
            continue
        for raw_id, raw in problems.items():
            if not isinstance(raw, Mapping):
                continue
            qid = str(raw_id)
            current = result.setdefault(qid, dict(raw))
            tags = set(current.get("contestTags", []) if isinstance(current.get("contestTags"), list) else [])
            tags.update(raw.get("contestTags", []) if isinstance(raw.get("contestTags"), list) else [])
            current["contestTags"] = sorted(str(tag) for tag in tags if str(tag).strip())
            # Prefer a non-empty title without a replacement character.
            title = str(raw.get("title") or "").strip()
            old_title = str(current.get("title") or "").strip()
            if title and (not old_title or "\ufffd" in old_title) and "\ufffd" not in title:
                current["title"] = title
            if not current.get("url") and raw.get("url"):
                current["url"] = raw.get("url")
    return result


# Explicit semantic matches.  The year in an ICPC/CCPC slug is the event year;
# it can differ from the export's startAt year by one (for example the 2022
# final is stored in the 2023 startAt slice).
TAG_OVERRIDES: dict[str, str] = {
    "ccpc/ccpc2021/ccpc2021final": "CCPC Final 2021",
    "ccpc/ccpc2022/ccpc2022final": "CCPC Final 2022",
    "ccpc/ccpc2023/ccpc2023final": "CCPC Final 2023",
    "ccpc/ccpc2024/ccpc2024final": "CCPC Final 2024",
    "ccpc/ccpc2025/ccpc2025final": "CCPC Final 2025",
    "ccpc/ccpc2022/ccpc2022guangzhou": "CCPC Guangzhou 2022",
    "ccpc/ccpc2022/ccpc2022guilin": "CCPC Guilin 2022",
    "ccpc/ccpc2022/ccpc2022mianyang": "CCPC Mianyang 2022",
    "ccpc/ccpc2022/ccpc2022preliminary": "CCPC Online 2022",
    "ccpc/ccpc2023/ccpc2023preliminary": "CCPC Online 2023",
    "ccpc/ccpc2024/ccpc2024chongqing": "CCPC Chongqing 2024",
    "ccpc/ccpc2024/ccpc2024jinan": "CCPC Jinan 2024",
    "ccpc/ccpc2025/ccpc2025jinan": "CCPC Jinan 2025",
    "icpc/icpc2022/icpc2022ecfinal": "EC-Final 2022",
    "icpc/icpc2023/icpc2023ecfinal": "EC-Final 2023",
    "icpc/icpc2024/icpc2024ecfinal": "EC-Final 2024",
    "icpc/icpc2025/icpc2025ecfinal": "EC-Final 2025",
    "icpc/icpc2023/icpc2023preliminary-1": "EC Online 2023 (I)",
    "icpc/icpc2024/icpc2024preliminary-2": "Asia EC Online 2024 (II)",
    "icpc/icpc2022/icpc2022hangzhou": "Hangzhou Regional 2022",
    "icpc/icpc2023/icpc2023hangzhou": "Hangzhou Regional 2023",
    "icpc/icpc2024/icpc2024hangzhou": "Hangzhou Regional 2024",
    "icpc/icpc2023/icpc2023hefei": "Hefei Regional 2023",
    "icpc/icpc2022/icpc2022jinan": "Jinan Regional 2022",
    "icpc/icpc2023/icpc2023jinan": "Jinan Regional 2023",
    "icpc/icpc2024/icpc2024nanjing": "Nanjing Regional 2024",
    "icpc/icpc2022/icpc2022nanjing": "Nanjing Regional 2022",
    "icpc/icpc2023/icpc2023nanjing": "Nanjing Regional 2023",
    "icpc/icpc2025/icpc2025nanjing": "Nanjing Regional 2025",
    "icpc/icpc2022/icpc2022shenyang": "Shenyang Regional 2022",
    "icpc/icpc2023/icpc2023shenyang": "Shenyang Regional 2023",
    "icpc/icpc2024/icpc2024shenyang": "Shenyang Regional 2024",
    "icpc/icpc2025/icpc2025shenyang": "Shenyang Regional 2025",
    "icpc/icpc2022/icpc2022xi_an": "Xi'an Regional 2022",
    "icpc/icpc2025/icpc2025xi_an": "Xi'an Regional 2025",
    "icpc/icpc2024/icpc2024chengdu": "Chengdu Regional 2024",
    "icpc/icpc2025/icpc2025chengdu": "Chengdu Regional 2025",
    "icpc/icpc2024/icpc2024shanghai": "Shanghai Regional 2024",
    "icpc/icpc2025/icpc2025shanghai": "Shanghai Regional 2025",
    "icpc/icpc2025/icpc2025wuhan": "Wuhan Regional 2025",
    "icpc/icpc2024/icpc2024kunming": "Kunming Regional 2024",
    "icpc/icpc2024/icpc2024invitational-kunming": "Kunming Invitational 2024",
    "icpc/icpc2025/icpc2025invitational-wuhan": "Wuhan Invitational 2025",
    "icpc/icpc2026/icpc2026invitational-shenzhen": "Shenzhen Invitational 2026",
    "provincial/gd/gdcpc20th": "Guangdong Provincial 2023",
    "provincial/gd/gdcpc21st": "Guangdong Provincial 2024",
    "provincial/gd/gdcpc23rd": "Guangdong Provincial 2026",
    "provincial/he/hecpc6th": "Hebei Provincial 2022",
    "provincial/he/hecpc7th": "Hebei Provincial 2023",
    "provincial/he/hecpc8th": "Hebei Provincial 2024",
    "provincial/he/hecpc9th": "Hebei Provincial 2025",
    "provincial/hl/hlcpc21st": "Heilongjiang Provincial 2026",
    "provincial/js/jscpc10th": "Jiangsu Provincial 2025",
    "provincial/js/jscpc11th": "Jiangsu Provincial 2026",
    # The source file used to contain replacement characters here.  QOJ's
    # actual tag is 辽宁省赛 2025; keep it escaped so the mapping survives
    # editors/terminals that cannot round-trip the Chinese glyphs.
    "provincial/ln/lncpc6th": "\u8fbd\u5b81\u7701\u8d5b 2025",
    "provincial/sd/sdcpc15th": "Shandong Provincial 2025",
    "provincial/sd/sdcpc16th": "Shandong Provincial 2026",
    "provincial/sc/sccpc16th": "Sichuan Provincial 2024",
    "provincial/sc/sccpc17th": "Sichuan Provincial 2025",
    "provincial/zj/zjcpc21st": "Zhejiang Provincial 2024",
    "provincial/zj/zjcpc23rd": "Zhejiang Provincial 2026",
    "ccpc/ccpc2026/ccpc2026invitational-fuzhou": "Fujian Provincial 2026",
}


def event_year(contest: str, fallback: int) -> int:
    matches = re.findall(r"20\d{2}", contest)
    return int(matches[-1]) if matches else fallback


def build() -> dict[str, Any]:
    aliases, metadata = target_contests()
    qoj = qoj_problem_union()
    tag_groups: dict[str, list[int]] = defaultdict(list)
    for raw_id, item in qoj.items():
        try:
            qid = int(raw_id)
        except ValueError:
            continue
        for tag in item.get("contestTags", []) if isinstance(item.get("contestTags"), list) else []:
            tag_groups[str(tag)].append(qid)
    for tag in tag_groups:
        tag_groups[tag] = sorted(set(tag_groups[tag]))

    # Start from the independent audit, then apply only explicit additions.
    proposed: dict[str, str] = {}
    independent = read_json(INDEPENDENT_PATH, {})
    if isinstance(independent, Mapping):
        for raw_key, value in independent.items():
            if str(raw_key).startswith("_") or not isinstance(value, Mapping):
                continue
            contest = str(raw_key).replace("__", "/")
            tag = str(value.get("tag") or "").strip()
            if contest and tag:
                proposed[contest] = tag
    proposed.update(TAG_OVERRIDES)

    output: dict[str, Any] = {}
    skipped: list[dict[str, Any]] = []
    for contest, target_aliases in sorted(aliases.items()):
        tag = proposed.get(contest)
        if not tag:
            skipped.append({"contestKey": contest, "reason": "no explicit QOJ contestTag mapping"})
            continue
        ids = tag_groups.get(tag, [])
        target_year = int(metadata.get(contest, {}).get("year") or 0)
        slug_year = event_year(contest, target_year)
        qoj_years = [int(x) for x in re.findall(r"20\d{2}", tag)]
        if len(ids) != len(target_aliases):
            skipped.append({"contestKey": contest, "tag": tag, "qojCount": len(ids), "targetCount": len(target_aliases), "reason": "problem count mismatch"})
            continue
        if qoj_years and qoj_years[-1] != slug_year:
            skipped.append({"contestKey": contest, "tag": tag, "qojYear": qoj_years[-1], "slugYear": slug_year, "reason": "event year mismatch"})
            continue
        if any(str(qid) not in qoj for qid in ids):
            skipped.append({"contestKey": contest, "tag": tag, "reason": "QOJ id missing from union index"})
            continue
        output[contest.replace("/", "__")] = {
            "tag": tag,
            "problemIds": ids,
            "targetAliases": target_aliases,
            "evidence": {
                "qojTag": tag,
                "qojCount": len(ids),
                "targetCount": len(target_aliases),
                "countMatch": True,
                "slugYear": slug_year,
                "startAtYear": target_year,
                "yearCheck": not qoj_years or qoj_years[-1] == slug_year,
                "sources": [
                    "web/public/data/problems-index.json",
                    "work/problem-audit/qoj-problem-index-2022-2026.json",
                    "work/problem-audit/qoj-problem-index-expanded.json",
                ],
            },
        }

    output["_meta"] = {
        "version": "qoj-assignments-final-v1",
        "generated": date.today().isoformat(),
        "criteria": "Explicit semantic contestTag mapping, exact target alias count, and slug-year check.",
        "assignmentCount": len([key for key in output if not key.startswith("_")]),
        "problemIdCount": sum(len(value["problemIds"]) for key, value in output.items() if not key.startswith("_")),
        "sources": [
            "web/public/data/problems-index.json",
            "work/problem-audit/qoj-problem-index-2022-2026.json",
            "work/problem-audit/qoj-problem-index-expanded.json",
            "work/problem-audit/qoj-assignments-independent-v2.json",
        ],
    }
    output["_skipped"] = skipped
    write_json(OUT_PATH, output)
    return output["_meta"] | {"skippedCount": len(skipped)}


if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False, indent=2))
