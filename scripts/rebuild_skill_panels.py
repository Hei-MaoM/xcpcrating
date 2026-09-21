"""Rebuild 13-axis sequential-IRT skill panels from current problem tags.

This does not replay the rating engine.  It reuses exported problem ratings and
player/team pre-ratings, then applies ``labels_from_detail_tags`` + sequential
IRT so player skill scores only use the updated 13-axis calculation.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from xcpc_rating.export_web import (  # noqa: E402
    _dump_json,
    _write_skill_leaderboard_assets,
    build_skill_leaderboard_index,
    player_shard,
)
from xcpc_rating.loader import SRK_SUFFIX  # noqa: E402
from xcpc_rating.panel_metrics import status_is_solved  # noqa: E402
from xcpc_rating.problem_tags import labels_from_detail_tags, normalize_detail_tags  # noqa: E402
from xcpc_rating.problem_types import (  # noqa: E402
    PROBLEM_TYPE_AXES,
    PROBLEM_TYPE_LABELS,
    normalize_label_weights,
    validate_problem_manifest,
)
from xcpc_rating.skill_panel import (  # noqa: E402
    SKILL_SCORE_MODEL,
    build_player_skill_panels,
    compact_player_skill_panels,
)

MANIFEST_PATH = ROOT / "data" / "problem-types" / "2023-present-all-qoj-v2.json"
PUBLIC = ROOT / "web" / "public" / "data"
PREVIEW = ROOT / "web" / "public" / "preview-data"
SRK_ROOT = ROOT / "vendor" / "srk-collection" / "official"
TAXONOMY_VERSION = "problem-types-audited-v4"
QUEUE_PATH = ROOT / "tmp" / "retag" / "queue.json"


def _skill_contest_ids() -> tuple[str, ...]:
    queue = json.loads(QUEUE_PATH.read_text(encoding="utf-8"))
    ids = [
        item["contestKey"]
        for item in queue.get("items") or []
        if item.get("status") == "applied" and item.get("contestKey")
    ]
    if not ids:
        raise SystemExit(f"no applied contests in {QUEUE_PATH}")
    return tuple(ids)


SKILL_CONTEST_IDS = _skill_contest_ids()
SKILL_SOURCE_WINDOW = (
    f"2022-2026 retagged final/regional/online ({len(SKILL_CONTEST_IDS)} contests); "
    "13-axis sequential IRT"
)


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _contest_slug(contest_id: str) -> str:
    return contest_id.replace("/", "__")


def _load_contest(contest_id: str):
    slug = f"{_contest_slug(contest_id)}.json"
    for root in (PREVIEW / "contests", PUBLIC / "contests"):
        path = root / slug
        if path.exists():
            payload = _load_json(path)
            if isinstance(payload, dict):
                return payload
    return None


def _problem_labels(problem: dict, curated: dict) -> dict[str, float]:
    tags = problem.get("detailTags") or curated.get("detailTags") or []
    labels = {}
    if tags:
        labels = labels_from_detail_tags(normalize_detail_tags(tags))
    if not labels:
        labels = {
            axis: weight
            for axis, weight in (curated.get("labels") or {}).items()
            if axis in PROBLEM_TYPE_AXES
        }
    if not labels:
        return {}
    return normalize_label_weights(labels)


def relabel_manifest() -> dict:
    manifest = _load_json(MANIFEST_PATH)
    empty_classified = 0
    for record in manifest.get("problems", {}).values():
        if not isinstance(record, dict):
            continue
        tags = record.get("detailTags") or []
        labels = {}
        if tags:
            labels = labels_from_detail_tags(normalize_detail_tags(tags))
        if not labels:
            labels = {
                axis: weight
                for axis, weight in (record.get("labels") or {}).items()
                if axis in PROBLEM_TYPE_AXES
            }
        if labels:
            record["labels"] = {
                axis: round(weight, 6)
                for axis, weight in normalize_label_weights(labels).items()
            }
        elif record.get("status") == "classified":
            empty_classified += 1
            record["status"] = "unknown"
            record["labels"] = {}
    manifest["version"] = TAXONOMY_VERSION
    manifest["axes"] = [
        {"key": axis, "label": PROBLEM_TYPE_LABELS[axis]}
        for axis in PROBLEM_TYPE_AXES
    ]
    validate_problem_manifest(manifest)
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"manifest {TAXONOMY_VERSION}: {len(manifest.get('problems', {}))} problems, "
        f"reclassified_empty={empty_classified}",
        flush=True,
    )
    return manifest


def _pre_ratings(history: list) -> tuple[dict[str, float], dict[str, float]]:
    all_map: dict[str, float] = {}
    official_map: dict[str, float] = {}
    previous = None
    previous_official = None
    for row in history or []:
        if not isinstance(row, dict):
            continue
        contest_id = str(row.get("contestId") or "")
        if contest_id:
            if previous is not None:
                all_map[contest_id] = previous
            if previous_official is not None:
                official_map[contest_id] = previous_official
        mu = row.get("mu_after")
        rating = row.get("rating_after")
        value = mu if isinstance(mu, (int, float)) else rating
        if isinstance(value, (int, float)):
            previous = float(value)
        if row.get("official"):
            official_mu = row.get("muAfterOfficial")
            official_rating = row.get("ratingAfterOfficial")
            official_value = (
                official_mu if isinstance(official_mu, (int, float)) else official_rating
            )
            if isinstance(official_value, (int, float)):
                previous_official = float(official_value)
    return all_map, official_map


def load_player_records() -> dict[str, dict]:
    records: dict[str, dict] = {}
    root = PUBLIC / "players"
    for path in sorted(root.glob("*.json")):
        bucket = _load_json(path)
        if isinstance(bucket, dict):
            records.update(bucket)
    print(f"loaded {len(records)} player records", flush=True)
    return records


def rebuild_skill_panels(manifest: dict, records: dict[str, dict]) -> dict:
    problems = manifest.get("problems") or {}
    evidence_by_player: dict[str, list[dict]] = {key: [] for key in records}
    pre_by_player = {
        key: _pre_ratings(record.get("history") or [])
        for key, record in records.items()
    }

    used = 0
    skipped = 0
    used_problems: set[str] = set()
    started = time.perf_counter()
    for index, contest_id in enumerate(SKILL_CONTEST_IDS, start=1):
        contest = _load_contest(contest_id)
        srk_path = SRK_ROOT / f"{contest_id}{SRK_SUFFIX}"
        if not isinstance(contest, dict) or not srk_path.exists():
            skipped += 1
            print(f"skip {contest_id}: missing contest or srk", flush=True)
            continue
        raw = _load_json(srk_path)
        raw_rows = raw.get("rows") if isinstance(raw, dict) else None
        teams = contest.get("teams") if isinstance(contest, dict) else None
        contest_problems = contest.get("problems") if isinstance(contest, dict) else None
        if not isinstance(raw_rows, list) or not isinstance(teams, list) or not isinstance(contest_problems, list):
            skipped += 1
            print(f"skip {contest_id}: malformed rows/teams/problems", flush=True)
            continue
        start_at = contest.get("startAt")
        tier = contest.get("tier") or "regional"
        used += 1
        limit = min(len(raw_rows), len(teams))
        for team_index in range(limit):
            team = teams[team_index]
            raw_row = raw_rows[team_index]
            if not isinstance(team, dict) or not isinstance(raw_row, dict):
                continue
            members = team.get("members") or []
            if not isinstance(members, list) or not members:
                continue
            statuses = raw_row.get("statuses")
            if not isinstance(statuses, list):
                statuses = []
            official = bool(team.get("official", True))
            team_pre = team.get("preRating")
            team_pre = float(team_pre) if isinstance(team_pre, (int, float)) else None
            member_weight = 1.0 / len(members)
            for problem_index, problem in enumerate(contest_problems):
                if not isinstance(problem, dict):
                    continue
                alias = str(problem.get("alias") or "")
                curated = problems.get(f"{contest_id}:{alias}")
                if not isinstance(curated, dict):
                    continue
                status = problem.get("status") or curated.get("status")
                labels = _problem_labels(problem, curated)
                if status != "classified" or not labels:
                    continue
                problem_rating = problem.get("problemRating")
                if not isinstance(problem_rating, (int, float)):
                    continue
                status_row = statuses[problem_index] if problem_index < len(statuses) else None
                solved = status_is_solved(status_row) if isinstance(status_row, dict) else None
                if solved is None:
                    continue
                canonical = str(
                    curated.get("canonicalId")
                    or problem.get("canonicalId")
                    or f"{contest_id}:{alias}"
                )
                confidence = float(
                    problem.get("confidence")
                    if isinstance(problem.get("confidence"), (int, float))
                    else curated.get("confidence") or 1.0
                )
                discrimination = problem.get("ratingDiscrimination", 1.0)
                if not isinstance(discrimination, (int, float)):
                    discrimination = 1.0
                identity = f"{contest_id}:{alias}"
                used_problems.add(identity)
                for member in members:
                    if not isinstance(member, dict):
                        continue
                    key = member.get("key")
                    if key not in evidence_by_player:
                        continue
                    all_pre, official_pre = pre_by_player.get(key, ({}, {}))
                    player_pre = official_pre.get(contest_id) if official else all_pre.get(contest_id)
                    if player_pre is None:
                        player_pre = all_pre.get(contest_id, team_pre)
                    evidence_by_player[key].append(
                        {
                            "contestId": contest_id,
                            "contestStartAt": start_at,
                            "tier": tier,
                            "official": official,
                            "canonicalId": canonical,
                            "identityKey": identity,
                            "labels": labels,
                            "status": "classified",
                            "classificationConfidence": confidence,
                            "difficultyWeight": 1.0,
                            "teamPreRating": team_pre,
                            "playerPreRating": player_pre,
                            "evidenceWeight": member_weight,
                            "solved": solved,
                            "problemRating": float(problem_rating),
                            "problemDiscrimination": float(discrimination),
                        }
                    )
        print(
            f"contests {index}/{len(SKILL_CONTEST_IDS)} used={used} skipped={skipped} "
            f"problems={len(used_problems)} elapsed={time.perf_counter() - started:.1f}s",
            flush=True,
        )

    with_evidence = sum(1 for items in evidence_by_player.values() if items)
    print(
        f"players with evidence: {with_evidence}; classified problems used: {len(used_problems)}",
        flush=True,
    )
    build_player_skill_panels(
        records,
        evidence_by_player,
        taxonomy_version=TAXONOMY_VERSION,
    )
    compact_player_skill_panels(records)
    print("skill panels compacted", flush=True)
    return {
        "usedContests": used,
        "skippedContests": skipped,
        "skillProblemCount": len(used_problems),
        "playersWithEvidence": with_evidence,
    }


def write_preview(manifest: dict, records: dict[str, dict], *, skill_problem_count: int) -> None:
    shards: dict[str, dict] = {}
    for key, record in records.items():
        shards.setdefault(player_shard(key), {})[key] = record

    meta_path = PUBLIC / "meta.json"
    meta = _load_json(meta_path) if meta_path.exists() else {}
    meta["skillTaxonomyVersion"] = TAXONOMY_VERSION
    meta["skillScoreModel"] = SKILL_SCORE_MODEL
    meta["skillScoreScale"] = "rating"
    meta["skillSourceWindow"] = SKILL_SOURCE_WINDOW
    meta["skillProblemCount"] = skill_problem_count
    meta["skillAxes"] = [
        {"key": axis, "label": PROBLEM_TYPE_LABELS[axis]}
        for axis in PROBLEM_TYPE_AXES
    ]

    for root in (PREVIEW, PUBLIC):
        players_root = root / "players"
        players_root.mkdir(parents=True, exist_ok=True)
        for shard, bucket in shards.items():
            _dump_json(str(players_root / f"{shard}.json"), bucket)
        skill_root = root / "skill-leaderboards"
        skill_root.mkdir(parents=True, exist_ok=True)
        _dump_json(str(skill_root / "index.json"), build_skill_leaderboard_index(records))
        _write_skill_leaderboard_assets(str(root), records)
        for stale in (
            skill_root / "all" / "overall" / "basic.json",
            skill_root / "official" / "overall" / "basic.json",
        ):
            if stale.exists():
                stale.unlink()
        _dump_json(str(root / "meta.json"), meta)
        print(f"wrote {root}", flush=True)


def main() -> int:
    started = time.perf_counter()
    manifest = _load_json(MANIFEST_PATH)
    records = load_player_records()
    for record in records.values():
        record.pop("skillPanel", None)
    stats = rebuild_skill_panels(manifest, records)
    write_preview(
        manifest,
        records,
        skill_problem_count=stats["skillProblemCount"],
    )
    print(
        f"window {SKILL_SOURCE_WINDOW}; contests={stats['usedContests']} "
        f"problems={stats['skillProblemCount']} players={stats['playersWithEvidence']}",
        flush=True,
    )
    sample = next(
        (
            record
            for record in records.values()
            if isinstance((record.get("skillPanel") or {}).get("all"), dict)
            and (record["skillPanel"]["all"].get("overall") or {}).get("axes")
        ),
        None,
    )
    if sample:
        panel = sample["skillPanel"]["all"]["overall"]
        print(
            "sample",
            sample.get("name"),
            "axes",
            len(panel.get("axes") or []),
            "model",
            panel.get("scoreModel"),
            "version",
            panel.get("taxonomyVersion"),
        )
    print(f"done in {time.perf_counter() - started:.1f}s", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
