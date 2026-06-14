#!/usr/bin/env python3
"""Crawl a PTA (pintia.cn) ``/rankings/<id>`` board into Standard Ranklist srk.

Self-contained (stdlib only). Uses the public PTA competition API:

  GET /api/competitions/{cid}/xcpc-rankings/public?filter={"teamExcluded":"NOT_FILTER"}
  GET /api/competitions/{cid}/groups

Per-problem AC / RJ / FB / tries / time are reconstructed from the public
``detailsByProblemSetProblemId`` summary (AC iff ``acceptTime >= 0``), so no
per-team submission timeline crawl is needed. Medal boundaries are not exposed
by PTA, so the medal series carries no count (recorded in ``remarks``).

Usage:
    python3 scripts/pta_to_srk.py <cid> -o <output.srk.json> [--contributor "Name (url)"]
"""
import argparse
import datetime as dt
import json
import subprocess
import sys
import urllib.parse

API = "https://pintia.cn/api/competitions"
UA = "algoUXRankSpiderCraft/1.0"
FILTER = urllib.parse.quote(json.dumps({"teamExcluded": "NOT_FILTER"}))
CST = dt.timezone(dt.timedelta(hours=8))
MARKER_PRESETS = ["blue", "green", "yellow", "orange", "red", "purple"]
SKIP_GROUPS = {"正式", "正式队", "正式队伍", "打星", "打星队", "打星队伍"}


def fetch(url):
    # Fetch via curl: it honours the system/corporate cert store (a self-signed
    # proxy CA in the chain breaks Python's own SSL verification here) and
    # transparently decompresses with --compressed.
    out = subprocess.run(
        ["curl", "-sS", "-m", "60", "--compressed", "-H", f"User-Agent: {UA}",
         "-H", "Accept: application/json", url],
        capture_output=True, check=True,
    )
    return json.loads(out.stdout)


def to_cst(iso_utc):
    parsed = dt.datetime.fromisoformat(iso_utc.replace("Z", "+00:00"))
    return parsed.astimezone(CST).strftime("%Y-%m-%dT%H:%M:%S+08:00")


def duration_minutes(start_iso, end_iso):
    start = dt.datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
    end = dt.datetime.fromisoformat(end_iso.replace("Z", "+00:00"))
    return int((end - start).total_seconds() // 60)


def build_markers(groups):
    female_fid = next((g["fid"] for g in groups if g.get("name") == "女队"), None)
    markers = []
    preset_idx = 0
    for group in groups:
        if group.get("name") in SKIP_GROUPS:
            continue
        if group["fid"] == female_fid:
            markers.append({"id": "female", "label": group["name"], "style": "pink"})
        else:
            markers.append({"id": group["fid"], "label": group["name"],
                            "style": MARKER_PRESETS[preset_idx % len(MARKER_PRESETS)]})
            preset_idx += 1
    # 女队 marker sorts last for display.
    for i, m in enumerate(markers):
        if m["id"] == "female":
            markers.append(markers.pop(i))
            break
    return markers, female_fid


def build_problems(problem_info):
    probs = sorted(
        ({"id": pid, **problem_info[pid]} for pid in problem_info),
        key=lambda p: p["label"],
    )
    out = []
    for p in probs:
        item = {"alias": p["label"],
                "statistics": {"accepted": p.get("acceptCount", 0),
                               "submitted": p.get("submitCount", 0)}}
        if p.get("balloonRgb"):
            item["style"] = {"backgroundColor": p["balloonRgb"]}
        out.append(item)
    return probs, out


def build_row(entry, probs, problem_info, marker_ids, female_fid, warnings):
    info = entry["teamInfo"]
    details = entry["detailsByProblemSetProblemId"]
    statuses = []
    ac_count = 0
    for p in probs:
        summary = details.get(p["id"])
        if not summary or summary.get("validSubmitCount", 0) == 0:
            statuses.append({"result": None})
            continue
        tries = summary["validSubmitCount"]
        accept_time = summary.get("acceptTime", -1)
        is_ac = accept_time is not None and accept_time >= 0
        if is_ac:
            ac_count += 1
            is_fb = problem_info[p["id"]].get("firstAcceptTeamFid") == entry["teamFid"]
            status = {"result": "FB" if is_fb else "AC", "tries": tries,
                      "time": [accept_time, "min"]}
        else:
            status = {"result": "RJ", "tries": tries}
        statuses.append(status)
    if ac_count != entry["solvedCount"]:
        warnings.append(
            f"team {entry['teamFid']} ({info.get('teamName')}): reconstructed "
            f"AC count {ac_count} != solvedCount {entry['solvedCount']}")
    user_markers = []
    for fid in info.get("groupFids", []):
        mid = "female" if fid == female_fid else fid
        if mid in marker_ids:
            user_markers.append(mid)
    user = {"id": entry["teamFid"], "name": info["teamName"],
            "organization": info.get("schoolName", ""),
            "teamMembers": [{"name": n} for n in info.get("memberNames", [])],
            "official": not info.get("excluded", False)}
    if user_markers:
        user["markers"] = user_markers
    return {"user": user,
            "score": {"value": entry["solvedCount"], "time": [entry["solvingTime"], "min"]},
            "statuses": statuses}


def build_srk(cid, contributor):
    pub = fetch(f"{API}/{cid}/xcpc-rankings/public?filter={FILTER}")
    try:
        groups = fetch(f"{API}/{cid}/groups").get("groups", [])
    except Exception:
        groups = []
    basic = pub["competitionBasicInfo"]
    xr = pub["xcpcRankings"]
    problem_info = xr["problemInfoByProblemSetProblemId"]
    probs, problems = build_problems(problem_info)
    markers, female_fid = build_markers(groups)
    marker_ids = {m["id"] for m in markers}
    warnings = []
    rows = [build_row(e, probs, problem_info, marker_ids, female_fid, warnings)
            for e in xr["rankings"]]
    srk = {
        "type": "general",
        "version": "0.3.2",
        "contest": {
            "title": {"zh-CN": basic["name"], "fallback": basic["name"]},
            "startAt": to_cst(basic["startAt"]),
            "duration": [duration_minutes(basic["startAt"], basic["endAt"]), "min"],
            "frozenDuration": [60, "min"],
            "refLinks": [{"link": f"https://pintia.cn/rankings/{cid}", "title": "原始榜单"}],
        },
        "problems": problems,
        "series": [
            {"title": "#",
             "segments": [{"title": "金奖", "style": "gold"},
                          {"title": "银奖", "style": "silver"},
                          {"title": "铜奖", "style": "bronze"}],
             "rule": {"preset": "ICPC", "options": {"count": {"value": [0, 0, 0]}}}},
            {"title": "R#", "rule": {"preset": "Normal"}},
            {"title": "S#", "rule": {"preset": "UniqByUserField",
                                     "options": {"field": "organization",
                                                 "includeOfficialOnly": True}}},
        ],
        "markers": markers,
        "sorter": {"algorithm": "ICPC", "config": {"penalty": [20, "min"]}},
        "rows": rows,
        "contributors": [contributor],
        "remarks": {
            "zh-CN": "本榜单由 pintia 公开数据爬取，缺少奖牌分界数据。",
            "fallback": "Crawled from pintia public data; medal boundaries unavailable.",
        },
    }
    return srk, warnings


def main():
    ap = argparse.ArgumentParser(description="PTA rankings -> srk.json")
    ap.add_argument("cid", help="PTA rankings id (the /rankings/<id> number)")
    ap.add_argument("-o", "--output", default="out.srk.json")
    ap.add_argument("--contributor", default="algoUX (https://algoux.org)")
    args = ap.parse_args()
    srk, warnings = build_srk(args.cid, args.contributor)
    with open(args.output, "w", encoding="utf-8") as fh:
        json.dump(srk, fh, ensure_ascii=False, indent=2)
    print(f"wrote {args.output}: {len(srk['rows'])} rows, "
          f"{len(srk['problems'])} problems")
    if warnings:
        print(f"WARNINGS ({len(warnings)}):", file=sys.stderr)
        for w in warnings[:20]:
            print("  " + w, file=sys.stderr)


if __name__ == "__main__":
    main()
