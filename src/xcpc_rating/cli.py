"""Command-line entry point: load -> replay -> leaderboard -> report."""

import argparse
import os
import sys
import time
from collections import Counter, defaultdict

from .engines import available_engines, get_engine
from .loader import load_contests
from .report import write_comparison, write_leaderboard
from .validate import replay

# Paths are resolved relative to the repo root (this file lives at
# src/xcpc_rating/cli.py). Source data is a git submodule (vendor/srk-collection);
# update it via scripts/update_data.sh.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_DATA = os.path.join(_REPO_ROOT, "vendor", "srk-collection", "official")
DEFAULT_OUT = os.path.join(_REPO_ROOT, "output")
DEFAULT_ENGINES = "incremental"
PROGRESS_EVERY = 20

# Sanity-check tuning: how deep into each board to inspect, and the
# strong-school name fragments to look for clustering.
SANITY_TOP = 50
STRONG_SCHOOLS = (
    "清华", "Tsinghua", "北京大学", "北大", "Peking",
    "上海交通", "上交", "Shanghai Jiao", "浙江大学", "浙大", "Zhejiang",
    "复旦", "Fudan", "南京大学", "Nanjing",
    "中国科学技术", "University of Science and Technology of China",
)
# A "suspicious" entry: only ever played provincial contests, very few of
# them, yet still surfaces near the top -- the designed failure sentinel.
SENTINEL_MAX_CONTESTS = 5


def build_parser():
    parser = argparse.ArgumentParser(
        prog="xcpc_rating",
        description="Compute contest player ratings and compare engines.",
    )
    parser.add_argument("--data", default=DEFAULT_DATA,
                        help="root of official srk collection")
    parser.add_argument("--out", default=DEFAULT_OUT,
                        help="output directory for reports")
    parser.add_argument("--engines", default=DEFAULT_ENGINES,
                        help="comma-separated engine names")
    parser.add_argument("--min-coverage", type=float, default=0.0,
                        help="optional extra member-list coverage floor; the "
                             "default 0.0 admits any board with >= 1 rostered "
                             "row (a no-roster board is always dropped)")
    parser.add_argument("--min-contests", type=int, default=1,
                        help="minimum rated contests to appear on a leaderboard "
                             "(default 1: a single rated contest earns a score)")
    parser.add_argument("--no-dedup", dest="dedup", action="store_false",
                        help="disable same-venue dual-board dedup")
    parser.set_defaults(dedup=True)
    return parser


def _parse_engine_names(raw):
    return [name.strip() for name in raw.split(",") if name.strip()]


class _ProgressReplay:
    """Wraps an engine to print progress every PROGRESS_EVERY contests."""

    def __init__(self, engine, label):
        self.engine = engine
        self.label = label
        self.name = engine.name
        self._count = 0

    def predict_scores(self, contest):
        return self.engine.predict_scores(contest)

    def process_contest(self, contest):
        self.engine.process_contest(contest)
        self._count += 1
        if self._count % PROGRESS_EVERY == 0:
            print(f"  [{self.label}] processed {self._count} contests",
                  flush=True)

    def leaderboard(self, min_contests=3):
        return self.engine.leaderboard(min_contests)


def _data_scale(load, min_contests):
    """Collect data-scale statistics from a load result.

    Returns a context fragment plus the player->category-count map (reused by
    the sanity check). Unique players and the >=N count are derived from the
    contests directly so they do not depend on any one engine.
    """
    player_cats = defaultdict(Counter)
    for contest in load.contests:
        for team in contest.teams:
            for member in team.members:
                player_cats[member.key][contest.category] += 1

    players_min = sum(
        1 for counts in player_cats.values()
        if sum(counts.values()) >= min_contests
    )
    loaded_by_category = dict(Counter(c.category for c in load.contests))
    years = sorted({c.start_at.year for c in load.contests})
    year_span = (years[0], years[-1]) if years else None

    # Bucket skips by reason so the report can separate the coverage gate from
    # same-venue dedup (dedup entries carry a "duplicate-of:" reason prefix).
    skipped_dedup = sum(
        1 for s in load.skipped
        if getattr(s, "reason", "").startswith("duplicate-of:")
    )
    skipped_coverage = len(load.skipped) - skipped_dedup

    fragment = {
        "loaded": len(load.contests),
        "skipped": len(load.skipped),
        "skipped_coverage": skipped_coverage,
        "skipped_dedup": skipped_dedup,
        "warnings": len(load.warnings),
        "loaded_by_category": loaded_by_category,
        "year_span": year_span,
        "unique_players": len(player_cats),
        "players_min_contests": players_min,
    }
    return fragment, player_cats


def _is_strong_school(org):
    return any(fragment in org for fragment in STRONG_SCHOOLS)


def _sanity_lines(results, player_cats):
    """Build the common-sense check markdown from the actual leaderboards.

    For each engine: count strong-school members in the top ``SANITY_TOP``, the
    dominant orgs, and any "provincial-only & few-contest" sentinel entries.
    """
    lines = [
        "在两份榜单 top%d 中核对知名强校选手聚集情况，并扫描"
        "\"只打省赛、场次很少却排名很高\" 的失真哨兵（设计中的预期失真）。\n"
        % SANITY_TOP
    ]
    for engine in results:
        board = results[engine]["leaderboard"][:SANITY_TOP]
        strong = 0
        orgs = Counter()
        sentinels = []
        for idx, player in enumerate(board, start=1):
            cats = player_cats.get(player.key, Counter())
            orgs[player.org] += 1
            if _is_strong_school(player.org):
                strong += 1
            only_provincial = set(cats) == {"provincial"}
            if only_provincial and player.contests <= SENTINEL_MAX_CONTESTS:
                sentinels.append(
                    f"#{idx} {player.display_name}@{player.org} "
                    f"(rating={player.rating:.1f}, contests={player.contests})"
                )
        top_orgs = ", ".join(f"{o}×{n}" for o, n in orgs.most_common(6))
        # Identical-rating clusters of size >= 2: when a whole team shares one
        # rating it surfaces as a teammate "trio" that rises or falls together.
        rating_clusters = Counter(round(p.rating, 2) for p in board)
        shared = sorted(
            (r for r, c in rating_clusters.items() if c >= 2), reverse=True
        )
        lines.append(f"### {engine}\n")
        lines.append(
            f"- 强校选手数 (top{SANITY_TOP}): **{strong} / {len(board)}**"
        )
        lines.append(f"- 主要来源院校: {top_orgs}")
        if shared:
            shared_str = ", ".join(f"{r:.2f}" for r in shared)
            lines.append(
                "- 同分队友簇（同队队员共享同一 rating，等量全额分摊的"
                f"指纹）: {shared_str}"
            )
        if sentinels:
            lines.append("- 失真哨兵 (只打省赛且场次 <= "
                         f"{SENTINEL_MAX_CONTESTS}): ")
            for entry in sentinels:
                lines.append(f"  - {entry}")
        else:
            lines.append(
                "- 失真哨兵: 无（top%d 内未出现只打省赛、场次极少却高分的条目）"
                % SANITY_TOP
            )
        lines.append("")
    return lines


def run(args):
    print(f"Loading contests from {args.data} "
          f"(min_coverage={args.min_coverage}, dedup={args.dedup}) ...",
          flush=True)
    load = load_contests(args.data, min_coverage=args.min_coverage,
                         dedup=args.dedup)
    dedup_skipped = [
        s for s in load.skipped
        if getattr(s, "reason", "").startswith("duplicate-of:")
    ]
    coverage_skipped = len(load.skipped) - len(dedup_skipped)
    print(f"Loaded {len(load.contests)} contests, "
          f"skipped {coverage_skipped} (coverage), "
          f"同场去重 {len(dedup_skipped)} 场, "
          f"{len(load.warnings)} warnings.", flush=True)

    engine_names = _parse_engine_names(args.engines)
    if not engine_names:
        print("No engines requested; nothing to do.", flush=True)
        return 0

    scale, player_cats = _data_scale(load, args.min_contests)
    print(f"Unique players: {scale['unique_players']}, "
          f">= {args.min_contests} contests: {scale['players_min_contests']}",
          flush=True)

    results = {}
    timings = {}
    for name in engine_names:
        print(f"\n=== Engine: {name} ===", flush=True)
        engine = _ProgressReplay(get_engine(name), name)
        started = time.perf_counter()
        metrics = replay(load.contests, engine)
        timings[name] = time.perf_counter() - started
        players = engine.leaderboard(min_contests=args.min_contests)
        write_leaderboard(name, players, args.out)
        results[name] = {"metrics": metrics, "leaderboard": players}
        overall = metrics["overall"]
        print(f"  players (>= {args.min_contests} contests): {len(players)}",
              flush=True)
        print(f"  replay_seconds={timings[name]:.2f} "
              f"concordance={overall['concordance']:.4f} "
              f"spearman={overall['spearman']:.4f}", flush=True)

    if len(results) >= 1:
        context = dict(scale)
        context["timings"] = timings
        context["sanity"] = _sanity_lines(results, player_cats)
        path = write_comparison(results, args.out, context=context)
        print(f"\nWrote comparison report: {path}", flush=True)

    print(f"\nReports written to {args.out}", flush=True)
    return 0


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return run(args)
    except KeyError as exc:
        print(f"error: {exc}", file=sys.stderr)
        print(f"available engines: {available_engines()}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
