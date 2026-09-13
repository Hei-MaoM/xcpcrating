#!/usr/bin/env python3
"""Fetch the public Codeforces Gym problem tables used by the audit.

The Gym dashboard exposes aliases and statement titles even when the individual
statement endpoint redirects to an attachment.  We keep the stable dashboard
evidence and emit a stable ``/gym/<id>/problem/<alias>`` link for each row.
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "work" / "problem-audit" / "cf-gym-problem-index.json"
INDEX = ROOT / "work" / "qoj-research" / "codeforces-gyms-index.json"

# Contest ids that correspond to the 2022--2026 target inventory or are useful
# fallbacks for a target whose original rank-board link is unavailable.
TARGET_GYMS = {
    103743, 103931, 103941, 104008, 104023, 104053, 104065, 104077,
    104090, 104128, 104160, 104337, 104354, 104369, 104385, 104396,
    104400, 104414, 104461, 104639, 104651, 104768, 104787, 104821,
    104857, 104869, 104901, 104976, 105139, 105143, 105158, 105161,
    105163, 105170, 105173, 105184, 105222, 105229, 105231, 105257,
    105336, 105358, 105385, 105386, 105401, 105459, 105471, 105481,
    105484, 105540, 105578, 105588, 105615, 105629, 105657, 105911,
    105924, 105941, 105945, 105949, 105977, 105981, 105992, 106030,
    106047, 106139, 106267, 106272, 106380, 106532, 106533, 106550,
    106551, 106554, 106562, 106565, 106570, 106589, 106689, 106695,
}


def clean_title(value: str) -> str:
    value = " ".join(value.replace("\xa0", " ").split()).strip()
    # The dashboard appends the I/O mode, limit and memory to the anchor text
    # in some locales.  They are presentation metadata, not part of the title.
    value = re.sub(r"\s+standard input/output\b.*$", "", value, flags=re.I)
    return value.strip()


def load_existing() -> dict:
    try:
        return json.loads(OUT.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {"source": "Codeforces Gym dashboard", "fetchedAt": None, "contests": {}}


def fetch(gid: int, session: requests.Session) -> dict:
    url = f"https://codeforces.com/gym/{gid}"
    for attempt in range(4):
        try:
            response = session.get(url, timeout=35)
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, "html.parser")
                title = soup.title.get_text(" ", strip=True) if soup.title else ""
                problems: dict[str, dict[str, str]] = {}
                for tr in soup.select("table tr"):
                    alias_node = tr.select_one('td.id a[href*="/problem/"]')
                    if not alias_node:
                        continue
                    alias = alias_node.get_text(" ", strip=True).upper()
                    title_cell = tr.select_one("td:nth-of-type(2)")
                    title_node = title_cell.select_one("a") if title_cell else None
                    problem_title = title_node.get_text(" ", strip=True) if title_node else (title_cell.get_text(" ", strip=True) if title_cell else "")
                    problem_title = clean_title(problem_title)
                    problems[alias] = {
                        "title": problem_title,
                        "problemUrl": f"https://codeforces.com/gym/{gid}/problem/{alias}",
                    }
                return {"name": title.replace("Dashboard - ", "", 1), "status": "ok", "problems": problems, "dashboardUrl": url}
            if response.status_code in {403, 429, 500, 502, 503, 504}:
                time.sleep(1.5 * (attempt + 1))
                continue
            return {"name": "", "status": f"http-{response.status_code}", "problems": {}, "dashboardUrl": url}
        except requests.RequestException as exc:
            if attempt == 3:
                return {"name": "", "status": f"error:{type(exc).__name__}", "problems": {}, "dashboardUrl": url}
            time.sleep(1.5 * (attempt + 1))
    return {"name": "", "status": "error", "problems": {}, "dashboardUrl": url}


def main() -> None:
    existing = load_existing()
    contests = existing.setdefault("contests", {})
    gym_catalog = {}
    try:
        payload = json.loads(INDEX.read_text(encoding="utf-8"))
        gym_catalog = payload.get("contests", {}) if isinstance(payload, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (metadata-audit/1.0)", "Accept-Language": "en-US,en;q=0.9"})
    for number, gid in enumerate(sorted(TARGET_GYMS), 1):
        old = contests.get(str(gid), {})
        # Refresh failed/empty pages and retain already good pages.  This makes
        # reruns cheap after a transient Codeforces rate limit.
        if old.get("status") == "ok" and old.get("problems"):
            continue
        item = fetch(gid, session)
        if not item.get("name") and str(gid) in gym_catalog:
            item["name"] = gym_catalog[str(gid)]
        contests[str(gid)] = item
        print(f"{number}/{len(TARGET_GYMS)} gym/{gid}: {item.get('status')} {len(item.get('problems', {}))}")
        time.sleep(0.35)
    existing["fetchedAt"] = datetime.now(timezone.utc).isoformat()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(existing, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"contests": len(contests), "ok": sum(v.get("status") == "ok" for v in contests.values()), "problems": sum(len(v.get("problems", {})) for v in contests.values())}, ensure_ascii=False))


if __name__ == "__main__":
    main()
