#!/usr/bin/env python3
"""Crawl an xcpcio board (board.xcpcio.com) into Standard Ranklist srk.

Self-contained (stdlib only; fetches via curl so the corporate proxy CA in the
chain does not break TLS). Reads the three public xcpcio artifacts:

  https://board.xcpcio.com/data/<path>/config.json
  https://board.xcpcio.com/data/<path>/team.json
  https://board.xcpcio.com/data/<path>/run.json

and reconstructs each team's per-problem ICPC status (AC / RJ / FB, tries, time)
and total (solved, penalty) by replaying runs in timestamp order -- the same
calculation xcpcio itself renders. Medal data, when absent from config, is left
empty (these online qualifiers award no medals).

Usage:
    python3 scripts/xcpcio_to_srk.py <board-path> -o <output.srk.json>
    e.g. <board-path> = icpc/48th/online-qualification-1
"""
import argparse
import datetime as dt
import json
import subprocess
import sys

DATA_BASE = "https://board.xcpcio.com/data"
CST = dt.timezone(dt.timedelta(hours=8))
MARKER_PRESETS = ["blue", "green", "yellow", "orange", "red", "purple"]


def fetch(url):
    out = subprocess.run(
        ["curl", "-sS", "-m", "120", "--compressed", url],
        capture_output=True, check=True,
    )
    return json.loads(out.stdout)


def to_cst(unix_seconds):
    return dt.datetime.fromtimestamp(unix_seconds, CST).strftime(
        "%Y-%m-%dT%H:%M:%S+08:00")


def build_statuses(team_id, runs_by_team, problem_count, penalty_seconds,
                   first_blood):
    """Per-problem ICPC status for one team, replaying its runs in time order."""
    statuses = [{"result": None} for _ in range(problem_count)]
    solved = 0
    total_time = 0
    runs = sorted(runs_by_team.get(team_id, []), key=lambda r: r["timestamp"])
    tries = [0] * problem_count
    done = [False] * problem_count
    for run in runs:
        pid = run["problem_id"]
        if pid >= problem_count or done[pid]:
            continue
        if run["status"].lower() == "correct":
            ts = run["timestamp"]
            penalty = penalty_seconds * tries[pid] + ts
            is_fb = first_blood.get(pid) == (team_id, ts)
            statuses[pid] = {"result": "FB" if is_fb else "AC",
                             "tries": tries[pid] + 1,
                             "time": [ts, "s"]}
            done[pid] = True
            solved += 1
            total_time += penalty
        else:
            tries[pid] += 1
            statuses[pid] = {"result": "RJ", "tries": tries[pid]}
    return statuses, solved, total_time


def compute_first_blood(runs, problem_count):
    """Earliest correct (team_id, timestamp) per problem -> first blood."""
    fb = {}
    for run in sorted(runs, key=lambda r: r["timestamp"]):
        pid = run["problem_id"]
        if run["status"].lower() == "correct" and pid < problem_count and pid not in fb:
            fb[pid] = (str(run["team_id"]), run["timestamp"])
    return fb


def build_srk(board_path, contributor):
    base = f"{DATA_BASE}/{board_path}"
    config = fetch(f"{base}/config.json")
    teams = fetch(f"{base}/team.json")
    runs = fetch(f"{base}/run.json")

    problem_ids = config["problem_id"]
    problem_count = len(problem_ids)
    penalty_seconds = int(config.get("penalty", 1200))
    start = int(config["start_time"])
    end = int(config["end_time"])
    if start > 10**12:  # ms -> s
        start //= 1000
        end //= 1000
    frozen = int(config.get("frozen_time", 0) or 0)
    if frozen > 10**12:
        frozen //= 1000

    runs_by_team = {}
    for run in runs:
        runs_by_team.setdefault(str(run["team_id"]), []).append(run)
    first_blood = compute_first_blood(runs, problem_count)

    balloon = config.get("balloon_color") or []
    problems = []
    for i, label in enumerate(problem_ids):
        item = {"alias": label}
        if i < len(balloon) and balloon[i].get("background_color"):
            item["style"] = {"backgroundColor": balloon[i]["background_color"]}
        problems.append(item)

    has_female = any(t.get("girl") for t in teams.values())
    markers = [{"id": "female", "label": "女队", "style": "pink"}] if has_female else []

    medal = config.get("medal") or {}
    official_medal = medal.get("official") or {}
    gold = int(official_medal.get("gold", 0))
    silver = int(official_medal.get("silver", 0))
    bronze = int(official_medal.get("bronze", 0))

    rows = []
    for team_id, team in teams.items():
        statuses, solved, total_time = build_statuses(
            team_id, runs_by_team, problem_count, penalty_seconds, first_blood)
        user = {"id": str(team_id), "name": team["name"],
                "organization": team.get("organization", ""),
                "teamMembers": [{"name": n} for n in (team.get("members") or [])],
                "official": team.get("official", 0) == 1}
        if team.get("girl"):
            user["markers"] = ["female"]
        rows.append({"user": user,
                     "score": {"value": solved, "time": [total_time, "s"]},
                     "statuses": statuses})
    rows.sort(key=lambda r: (-r["score"]["value"], r["score"]["time"][0]))

    srk = {
        "type": "general",
        "version": "0.3.2",
        "contest": {
            "title": {"zh-CN": config["contest_name"], "fallback": config["contest_name"]},
            "startAt": to_cst(start),
            "duration": [int((end - start) // 60), "min"],
            "frozenDuration": [int(frozen // 60), "min"],
            "refLinks": [{"link": f"https://board.xcpcio.com/{board_path}",
                          "title": "原始榜单"}],
        },
        "problems": problems,
        "series": [
            {"title": "#",
             "segments": [{"title": "金奖", "style": "gold"},
                          {"title": "银奖", "style": "silver"},
                          {"title": "铜奖", "style": "bronze"}],
             "rule": {"preset": "ICPC",
                      "options": {"count": {"value": [gold, silver, bronze]}}}},
            {"title": "R#", "rule": {"preset": "Normal"}},
            {"title": "S#", "rule": {"preset": "UniqByUserField",
                                     "options": {"field": "organization",
                                                 "includeOfficialOnly": True}}},
        ],
        "markers": markers,
        "sorter": {"algorithm": "ICPC",
                   "config": {"penalty": [penalty_seconds // 60, "min"]}},
        "rows": rows,
        "contributors": [contributor],
        "remarks": {
            "zh-CN": "本榜单由 xcpcio 公开数据爬取。",
            "fallback": "Crawled from xcpcio public data.",
        },
    }
    return srk


def main():
    ap = argparse.ArgumentParser(description="xcpcio board -> srk.json")
    ap.add_argument("board_path", help="e.g. icpc/48th/online-qualification-1")
    ap.add_argument("-o", "--output", default="out.srk.json")
    ap.add_argument("--contributor",
                    default="XCPCIO (https://xcpcio.com/), algoUX (https://algoux.org)")
    args = ap.parse_args()
    srk = build_srk(args.board_path, args.contributor)
    with open(args.output, "w", encoding="utf-8") as fh:
        json.dump(srk, fh, ensure_ascii=False, indent=2)
    print(f"wrote {args.output}: {len(srk['rows'])} rows, "
          f"{len(srk['problems'])} problems, "
          f"title={srk['contest']['title']['zh-CN']}")


if __name__ == "__main__":
    main()
