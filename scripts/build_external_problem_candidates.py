#!/usr/bin/env python3
"""Build reviewable single-problem candidates from public mirrors.

QOJ assignments remain the preferred source in ``merge_problem_audit.py``.
This file supplies independent Codeforces Gym and Atuer candidates for target
contests whose SRK file only contains a rank board (or no link at all).  The
mapping is explicit so a similarly named contest can never be shifted onto a
different target by fuzzy matching.
"""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup
import requests

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "work" / "problem-audit"
RESEARCH = ROOT / "work" / "qoj-research"
TARGET_INDEX = ROOT / "web" / "public" / "data" / "problems-index.json"
OUT = AUDIT / "external-problem-candidates.json"
CF_INDEX = AUDIT / "cf-gym-problem-index.json"
TARGET_CONTESTS_PATH = AUDIT / "target-contests-full.tsv"

# Exact contest-name matches from the Codeforces Gym index.  Reusing one Gym
# for two slugs is intentional only where the source itself names the same
# combined contest (for example the Jiangxi provincial and Nanchang invitational
# rows).
CF_ASSIGNMENTS: dict[str, int] = {
    # 2025
    "ccpc/ccpc2025/ccpc2025invitational-fujian": 105977,
    "ccpc/ccpc2025/ccpc2025invitational-northeast": 105924,
    "ccpc/ccpc2025/ccpc2025invitational-zhengzhou": 105941,
    "ccpc/ccpc2025/ccpc2025invitational-guangdong-preliminary": 105945,
    "icpc/icpc2025/icpc2025invitational-nanchang": 105911,
    "provincial/jx/jxcpc2025": 105911,
    "provincial/sh/shcpc2025": 105992,
    # 2024
    "ccpc/ccpc2024/ccpc2024invitational-jinan": 105385,
    "ccpc/ccpc2024/ccpc2024ladies": 105487,
    "icpc/icpc2024/icpc2024invitational-wuhan": 105143,
    "icpc/icpc2024/icpc2024invitational-kunming": 105386,
    "icpc/icpc2024/icpc2024kunming": 105588,
    "ccpc/ccpc2024/ccpc2024preliminary": 105336,
    "provincial/ln/lncpc5th": 105481,
    "provincial/sh/shcpc2024": 105229,
    "provincial/sc/sccpc16th": 105222,
    # 2023
    "ccpc/ccpc2023/ccpc2023invitational-xiangtan": 104396,
    "provincial/hn/hncpc19th": 104400,
    # The SRK reference for Jinan was copied from the neighbouring Shenyang
    # regional.  Codeforces' official Gym dashboard identifies the Jinan set
    # as 104901; keep this explicit assignment ahead of raw ref-link fallback.
    "icpc/icpc2023/icpc2023jinan": 104901,
    # These two provincial events were held as one combined contest on
    # Codeforces.  Both slugs intentionally point to the same Gym/problem set.
    "provincial/gd/gdcpc23rd": 106550,
    "provincial/js/jscpc11th": 106550,
    # 2024 Henan collegiate contest (the Gym contains the target A-K set).
    "provincial/hn/hncpc20th": 105158,
    # 2022
    "provincial/js/jscpc7th": 103743,
    "ccpc/ccpc2022/ccpc2022guangzhou": 104053,
    "ccpc/ccpc2022/ccpc2022mianyang": 104065,
    "ccpc/ccpc2022/ccpc2022guilin": 104008,
    "ccpc/ccpc2022/ccpc2022weihai": 104023,
    # 2026 Qinhuangdao invitational; the Gym dashboard is the exact public
    # contest mirror and provides stable per-alias statement URLs.
    "ccpc/ccpc2026/ccpc2026invitational-qinhuangdao": 106695,
}

# Atuer has a clean problem page for the 2026 Qinhuangdao event.  The source
# is fetched once and stored in this candidate artifact; subsequent merges are
# offline and deterministic.
ATUER_CONTESTS: dict[str, str] = {
    "ccpc/ccpc2026/ccpc2026invitational-qinhuangdao": "https://www.atuer.cn/contest/6a169349985f2e7929398811",
    "ccpc/ccpc2026/ccpc2026invitational-nanchang": "https://www.atuer.cn/contest/6a16b1b7985f2e7929399fc1",
    "provincial/zj/zjcpc20th": "https://www.atuer.cn/contest/698ed56511ca5cdfe1153ea3",
    "ccpc/ccpc2022/ccpc2022hv": "https://www.atuer.cn/contest/6912d75751ad8a5edb58f7a5",
}


def read(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def clean(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    value = " ".join(value.replace("\xa0", " ").split()).strip()
    value = re.sub(r"\s+standard input/output\b.*$", "", value, flags=re.I)
    return value or None


def target_rows() -> dict[str, list[str]]:
    rows: dict[str, list[str]] = {}
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
    for item in read(TARGET_INDEX, []):
        if not isinstance(item, dict):
            continue
        try:
            year = int(str(item.get("startAt") or "")[:4])
        except ValueError:
            continue
        if year not in {2022, 2023, 2024, 2025, 2026}:
            continue
        key = str(item.get("contestSlug") or "").replace("__", "/")
        alias = str(item.get("alias") or "").upper()
        if key and alias:
            if allowed and key not in allowed:
                continue
            rows.setdefault(key, []).append(alias)
    return {key: sorted(set(value)) for key, value in rows.items()}


def cf_candidates(rows: dict[str, list[str]]) -> list[dict[str, Any]]:
    payload = read(CF_INDEX, {})
    contests = payload.get("contests", {}) if isinstance(payload, dict) else {}
    out: list[dict[str, Any]] = []
    selected = dict(CF_ASSIGNMENTS)
    # A raw Codeforces Gym reference is a safe explicit source even when the
    # original SRK ref was a standings page.  It is added only when all target
    # aliases exist in that Gym's dashboard.
    for contest in rows:
        if contest in selected:
            continue
        raw_path = ROOT / "vendor" / "srk-collection" / "official" / f"{contest}.srk.json"
        raw = read(raw_path, {})
        refs = (raw.get("contest") or {}).get("refLinks", []) if isinstance(raw, dict) else []
        for ref in refs if isinstance(refs, list) else []:
            link = ref.get("link") if isinstance(ref, dict) else ref
            if not isinstance(link, str):
                continue
            m = re.search(r"(?:gym|contest)/(\d+)", link)
            if m and m.group(1) in contests:
                selected[contest] = int(m.group(1))
                break
    for contest, gid in sorted(selected.items()):
        source = contests.get(str(gid), {})
        problems = source.get("problems", {}) if isinstance(source, dict) else {}
        aliases = rows.get(contest, [])
        if not aliases or not isinstance(problems, dict) or not all(alias in problems for alias in aliases):
            continue
        dashboard = source.get("dashboardUrl") or f"https://codeforces.com/gym/{gid}"
        source_name = clean(source.get("name")) or f"Codeforces Gym {gid}"
        for alias in aliases:
            item = problems.get(alias, {})
            title = clean(item.get("title") if isinstance(item, dict) else item)
            if not title:
                continue
            url = f"https://codeforces.com/gym/{gid}/problem/{alias}"
            out.append({
                "contestKey": contest,
                "alias": alias,
                "title": title,
                "problemUrl": url,
                "canonicalId": f"cf:gym:{gid}:{alias}",
                "sourceUrl": dashboard,
                "sourceKind": "codeforces-gym",
                "evidence": f"Codeforces Gym dashboard {dashboard}; contest={source_name}; alias={alias}; exact alias-set match.",
                "confidence": 0.97,
            })
    return out


def atuer_candidates(rows: dict[str, list[str]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (metadata-audit/1.0)"})
    for contest, contest_url in ATUER_CONTESTS.items():
        if contest not in rows:
            continue
        try:
            response = session.get(contest_url + "/problems", timeout=35)
            response.raise_for_status()
            # The response declares UTF-8; decode it explicitly instead of
            # letting a platform/default codec turn Chinese titles into
            # mojibake before BeautifulSoup sees them.
            html = response.content.decode("utf-8", "replace")
            soup = BeautifulSoup(html, "html.parser")
        except requests.RequestException:
            continue
        found: dict[str, tuple[str, str]] = {}
        for anchor in soup.select('td.col--problem-name a[href*="/p/"]'):
            text = " ".join(anchor.get_text(" ", strip=True).split())
            match = re.match(r"([A-Z])\s+(.+)$", text)
            if not match:
                continue
            alias, title = match.group(1), clean(match.group(2))
            if alias not in rows[contest] or not title:
                continue
            href = anchor.get("href")
            if not isinstance(href, str):
                continue
            if href.startswith("/"):
                href = "https://www.atuer.cn" + href
            # The problem links include the contest id as a query parameter;
            # retain it so the page remains tied to this event.
            found[alias] = (title, href)
        for alias in rows[contest]:
            if alias not in found:
                continue
            title, url = found[alias]
            out.append({
                "contestKey": contest,
                "alias": alias,
                "title": title,
                "problemUrl": url,
                "canonicalId": f"atu er:{contest}:{alias}".replace(" ", ""),
                "sourceUrl": contest_url + "/problems",
                "sourceKind": "atu er-contest".replace(" ", ""),
                "evidence": f"Atuer contest problem list {contest_url}/problems; direct problem page for alias {alias}.",
                "confidence": 0.99,
            })
    return out


def main() -> None:
    rows = target_rows()
    records = cf_candidates(rows) + atuer_candidates(rows)
    # Include the independent female-contest extraction as a second source;
    # duplicates are resolved by the merge priority and exact key.
    independent = read(AUDIT / "cf-candidates-reviewer1.json", {})
    if isinstance(independent, dict):
        records.extend(x for x in independent.get("records", []) if isinstance(x, dict))
        # The reviewer artifact uses ``candidates`` in older runs.
        for item in independent.get("candidates", []):
            if not isinstance(item, dict):
                continue
            item = dict(item)
            if isinstance(item.get("contestKey"), str):
                item["contestKey"] = item["contestKey"].replace("__", "/")
            item.setdefault("sourceKind", "codeforces-gym")
            records.append(item)
    records = [x for x in records if isinstance(x, dict) and x.get("contestKey") and x.get("alias")]
    source_kinds = sorted({str(x.get("sourceKind")) for x in records})
    payload = {
        "schemaVersion": "external-problem-candidates-v1",
        "generated": date.today().isoformat(),
        "sources": ["work/problem-audit/cf-gym-problem-index.json", "Atuer contest problem pages", "cf-candidates-reviewer1.json"],
        "records": records,
        "summary": {"records": len(records), "contests": len({x.get("contestKey") for x in records}), "sources": {k: sum(1 for x in records if x.get("sourceKind") == k) for k in source_kinds}},
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
