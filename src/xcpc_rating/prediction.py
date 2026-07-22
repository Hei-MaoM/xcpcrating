"""Pre-contest team and school predictions from a published roster.

The rating engine remains the single source of player strength.  This module
only takes a cutoff-time rating snapshot, matches roster members by the normal
``name@organization`` identity key, aggregates each team with the same LSE rule
used by the engine, and ranks the resulting field.  An unseen member receives
the normal 1400 newcomer prior, so predictions stay total even for a partially
matched roster.
"""

from __future__ import annotations

import json
import os
from datetime import datetime

from .engines.incremental import INITIAL_EXPECT, IncrementalEngine
from .identity import player_key
from .perf import lse_aggregate


MEDAL_COLORS = ("gold", "silver", "bronze")
MEDAL_TIERS = ("final", "regional", "invitational", "provincial")


def _round(value: float) -> float:
    return round(float(value), 2)


def rating_snapshot(engine) -> dict[str, float]:
    """Return ``player key -> current E`` from a finished replay engine."""
    return {
        key: float(state["expect"])
        for key, state in engine._players.items()  # noqa: SLF001 - export snapshot
    }


def load_prediction_specs(spec_dir: str) -> list[dict]:
    """Load and validate every ``*.json`` prediction roster in ``spec_dir``."""
    if not os.path.isdir(spec_dir):
        return []

    specs = []
    for name in sorted(os.listdir(spec_dir)):
        if not name.endswith(".json"):
            continue
        path = os.path.join(spec_dir, name)
        with open(path, "r", encoding="utf-8") as handle:
            spec = json.load(handle)
        _validate_spec(spec, path)
        specs.append(spec)
    return specs


def _validate_spec(spec: dict, path: str = "<prediction>") -> None:
    required = ("id", "slug", "title", "startAt", "category", "teams")
    missing = [key for key in required if not spec.get(key)]
    if missing:
        raise ValueError(f"{path}: missing prediction fields: {', '.join(missing)}")

    teams = spec["teams"]
    if not isinstance(teams, list) or not teams:
        raise ValueError(f"{path}: teams must be a non-empty list")
    numbers = [team.get("number") for team in teams]
    if any(not isinstance(number, int) for number in numbers):
        raise ValueError(f"{path}: every team needs an integer number")
    if len(numbers) != len(set(numbers)):
        raise ValueError(f"{path}: duplicate team number")
    for team in teams:
        if not team.get("name") or not team.get("org"):
            raise ValueError(f"{path}: team {team.get('number')} has no name/org")
        members = team.get("members")
        if not isinstance(members, list) or not members:
            raise ValueError(f"{path}: team {team.get('number')} has no members")


def _assign_ranks(rows: list[dict], strength_key: str, rank_key: str) -> None:
    """Assign stable 1224 ranks in place, strongest first."""
    rows.sort(key=lambda row: (-row[strength_key], row["number"]))
    previous = None
    current_rank = 0
    for position, row in enumerate(rows, start=1):
        strength = row[strength_key]
        if previous is None or strength != previous:
            current_rank = position
        row[rank_key] = current_rank
        previous = strength


def _flatten_medals(per_tier: dict | None) -> dict[str, int]:
    """Collapse a player's tiered medal history into gold/silver/bronze totals."""
    totals = {color: 0 for color in MEDAL_COLORS}
    for counts in (per_tier or {}).values():
        for color in MEDAL_COLORS:
            totals[color] += int(counts.get(color, 0))
    return totals


def _tiered_medals(per_tier: dict | None) -> dict[str, dict[str, int]]:
    """Normalize one player's medals to every ranking tier and color."""
    per_tier = per_tier or {}
    return {
        tier: {
            color: int((per_tier.get(tier) or {}).get(color, 0))
            for color in MEDAL_COLORS
        }
        for tier in MEDAL_TIERS
    }


def _assign_medal_ranks(rows: list[dict]) -> None:
    """Rank by prestige tier, then medal color; rating breaks exact ties."""
    rows.sort(
        key=lambda row: tuple(
            -row["historicalMedalsByTier"][tier][color]
            for tier in MEDAL_TIERS
            for color in MEDAL_COLORS
        )
        + (-row["officialStrength"], row["number"])
    )
    for position, row in enumerate(rows, start=1):
        row["medalRank"] = position


def _award_labels(prize: dict) -> list[str]:
    labels = []
    for award in prize.get("awards", []):
        labels.extend([str(award["label"])] * int(award["count"]))
    return labels


def build_prediction(
    spec: dict,
    all_ratings: dict[str, float],
    official_ratings: dict[str, float],
    medals: dict | None = None,
) -> dict:
    """Build one static prediction document from a roster specification.

    ``allRank`` ranks the complete field using the all-participation rating
    snapshot. ``officialRank`` removes starred teams and uses the independently
    replayed official-only snapshot. The school prize forecast takes each
    official school's strongest predicted team, matching the manual's award
    rule.
    """
    _validate_spec(spec)
    teams: list[dict] = []
    total_members = 0
    official_members = 0
    matched_members = 0
    matched_official_members = 0
    medals = medals or {}

    for source in spec["teams"]:
        member_docs = []
        all_strengths = []
        official_strengths = []
        team_medals = {color: 0 for color in MEDAL_COLORS}
        team_medals_by_tier = {
            tier: {color: 0 for color in MEDAL_COLORS}
            for tier in MEDAL_TIERS
        }
        for name in source["members"]:
            key = player_key(name, source["org"])
            matched = key in all_ratings
            matched_official = key in official_ratings
            all_rating = all_ratings.get(key, INITIAL_EXPECT)
            official_rating = official_ratings.get(key, INITIAL_EXPECT)
            member_docs.append(
                {
                    "key": key,
                    "name": name,
                    "matched": matched,
                    "matchedOfficial": matched_official,
                    "rating": _round(all_rating),
                    "officialRating": _round(official_rating),
                }
            )
            all_strengths.append(all_rating)
            official_strengths.append(official_rating)
            member_medals = _flatten_medals(medals.get(key))
            member_medals_by_tier = _tiered_medals(medals.get(key))
            for color in MEDAL_COLORS:
                team_medals[color] += member_medals[color]
            for tier in MEDAL_TIERS:
                for color in MEDAL_COLORS:
                    team_medals_by_tier[tier][color] += (
                        member_medals_by_tier[tier][color]
                    )
            total_members += 1
            matched_members += int(matched)
            if source.get("official", True):
                official_members += 1
                matched_official_members += int(matched_official)

        all_strength = lse_aggregate(all_strengths)
        official_strength = lse_aggregate(official_strengths)
        teams.append(
            {
                "number": source["number"],
                "name": source["name"],
                "org": source["org"],
                "seat": source.get("seat", ""),
                "official": bool(source.get("official", True)),
                "members": member_docs,
                "matchedMembers": sum(member["matched"] for member in member_docs),
                "matchedOfficialMembers": sum(
                    member["matchedOfficial"] for member in member_docs
                ),
                "allStrength": all_strength,
                "officialStrength": official_strength,
                "allRank": None,
                "officialRank": None,
                "historicalMedals": team_medals,
                "historicalMedalsByTier": team_medals_by_tier,
                "medalRank": None,
            }
        )

    _assign_ranks(teams, "allStrength", "allRank")

    official_teams = [team for team in teams if team["official"]]
    _assign_ranks(official_teams, "officialStrength", "officialRank")
    _assign_medal_ranks(official_teams)

    # One prize candidate per school: its strongest official team. Ties are
    # stable by registration number because the published award has fixed slots.
    best_by_school: dict[str, dict] = {}
    for team in official_teams:
        current = best_by_school.get(team["org"])
        if current is None or (
            team["officialStrength"], -team["number"]
        ) > (current["officialStrength"], -current["number"]):
            best_by_school[team["org"]] = team

    labels = _award_labels(spec.get("prize", {}))
    school_rows = []
    for position, team in enumerate(
        sorted(
            best_by_school.values(),
            key=lambda row: (-row["officialStrength"], row["number"]),
        ),
        start=1,
    ):
        school_rows.append(
            {
                "rank": position,
                "org": team["org"],
                "teamNumber": team["number"],
                "teamName": team["name"],
                "strength": team["officialStrength"],
                "award": labels[position - 1] if position <= len(labels) else None,
            }
        )

    # Rank and prize selection use full precision; only the public JSON values
    # are rounded for compact, stable output.
    for team in teams:
        team["allStrength"] = _round(team["allStrength"])
        team["officialStrength"] = _round(team["officialStrength"])
    for school in school_rows:
        school["strength"] = _round(school["strength"])

    # Return team rows in predicted all-field order. The official rank remains
    # available for switching caliber without another download.
    teams.sort(key=lambda row: (-row["allStrength"], row["number"]))
    official_count = sum(team["official"] for team in teams)
    return {
        "id": spec["id"],
        "slug": spec["slug"],
        "title": spec["title"],
        "shortTitle": spec.get("shortTitle", spec["title"]),
        "startAt": spec["startAt"],
        "category": spec["category"],
        "source": spec.get("source", ""),
        "sourceDate": spec.get("sourceDate"),
        "teamCount": len(teams),
        "officialTeamCount": official_count,
        "starredTeamCount": len(teams) - official_count,
        "totalMembers": total_members,
        "officialMembers": official_members,
        "matchedMembers": matched_members,
        "matchedOfficialMembers": matched_official_members,
        "priorRating": INITIAL_EXPECT,
        "prize": spec.get("prize", {}),
        "schools": school_rows,
        "teams": teams,
        "notes": [
            "预测只使用比赛开始前已经收录的历史积分，不使用未来赛果。",
            "队伍强度与评分引擎一致，按队员积分在 Elo 胜率空间做 LSE 聚合。",
            "未匹配到历史记录的选手按新人先验 1400 分处理。",
            "奖牌排序依次比较决赛、区域赛、邀请赛、省赛；每级内按金、银、铜比较，完全相同时按积分排序。",
        ],
    }


def build_predictions(spec_dir: str, contests, medals: dict | None = None) -> list[dict]:
    """Build predictions from rating snapshots strictly before each start time.

    Specifications are processed chronologically while a pair of engines advances
    once through the historical corpus. This keeps regeneration safe after the
    predicted event has happened: later contests can never leak into its forecast.
    """
    specs = sorted(
        load_prediction_specs(spec_dir),
        key=lambda spec: datetime.fromisoformat(spec["startAt"]),
    )
    engine = IncrementalEngine()
    official_engine = IncrementalEngine(official_only=True)
    contest_index = 0
    documents = []
    for spec in specs:
        cutoff = datetime.fromisoformat(spec["startAt"])
        while (
            contest_index < len(contests)
            and contests[contest_index].start_at < cutoff
        ):
            contest = contests[contest_index]
            engine.process_contest(contest)
            official_engine.process_contest(contest)
            contest_index += 1
        document = build_prediction(
            spec,
            rating_snapshot(engine),
            rating_snapshot(official_engine),
            medals=medals,
        )
        document["ratingCutoff"] = spec["startAt"]
        document["ratedContestCount"] = contest_index
        documents.append(document)
    return documents


def prediction_index_entry(document: dict) -> dict:
    """Compact list-page record for one full prediction document."""
    return {
        key: document[key]
        for key in (
            "id",
            "slug",
            "title",
            "shortTitle",
            "startAt",
            "category",
            "teamCount",
            "officialTeamCount",
            "starredTeamCount",
            "totalMembers",
            "matchedMembers",
        )
    }
