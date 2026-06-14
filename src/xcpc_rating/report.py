"""Leaderboard and comparison report writers (CSV / Markdown)."""

import csv
import os

TOP_CSV = 500
TOP_MD = 50
COMPARE_TOP = 30
OVERLAP_TOP = 100

_BASE_FIELDS = ["key", "display_name", "org", "rating", "contests"]


def _ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def _flatten_extra_keys(players):
    """Collect the union of extra keys across players, in stable order."""
    keys = []
    seen = set()
    for player in players:
        for key in player.extra:
            if key not in seen:
                seen.add(key)
                keys.append(key)
    return keys


def _round(value):
    if isinstance(value, float):
        return round(value, 2)
    return value


def write_leaderboard(engine_name, players, out_dir):
    """Write a top-500 CSV and a top-50 Markdown table for one engine.

    Returns (csv_path, md_path).
    """
    _ensure_dir(out_dir)
    extra_keys = _flatten_extra_keys(players)

    csv_path = os.path.join(out_dir, f"leaderboard_{engine_name}.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(_BASE_FIELDS + extra_keys)
        for player in players[:TOP_CSV]:
            row = [
                player.key,
                player.display_name,
                player.org,
                _round(player.rating),
                player.contests,
            ]
            row += [_round(player.extra.get(k, "")) for k in extra_keys]
            writer.writerow(row)

    md_path = os.path.join(out_dir, f"leaderboard_{engine_name}.md")
    with open(md_path, "w", encoding="utf-8") as handle:
        handle.write(f"# Leaderboard — {engine_name} (top {TOP_MD})\n\n")
        handle.write("| # | Player | Org | Rating | Contests |\n")
        handle.write("|---|--------|-----|--------|----------|\n")
        for idx, player in enumerate(players[:TOP_MD], start=1):
            handle.write(
                f"| {idx} | {player.display_name} | {player.org} | "
                f"{_round(player.rating)} | {player.contests} |\n"
            )

    return csv_path, md_path


def _fmt_metric(value):
    return "n/a" if value is None else f"{value:.4f}"


def _metrics_table(results):
    """Build the overall + per-category metrics comparison table."""
    lines = ["## Metrics\n"]
    engines = list(results)

    lines.append("### Overall\n")
    header = "| Engine | Concordance | Spearman | Contests |"
    sep = "|--------|-------------|----------|----------|"
    lines.append(header)
    lines.append(sep)
    for engine in engines:
        overall = results[engine]["metrics"]["overall"]
        lines.append(
            f"| {engine} | {_fmt_metric(overall['concordance'])} | "
            f"{_fmt_metric(overall['spearman'])} | {overall['contests']} |"
        )
    lines.append("")

    categories = set()
    for engine in engines:
        categories.update(results[engine]["metrics"]["by_category"])
    for category in sorted(categories):
        lines.append(f"### Category: {category}\n")
        lines.append("| Engine | Concordance | Spearman | Contests |")
        lines.append("|--------|-------------|----------|----------|")
        for engine in engines:
            stats = results[engine]["metrics"]["by_category"].get(category)
            if stats is None:
                lines.append(f"| {engine} | n/a | n/a | 0 |")
                continue
            lines.append(
                f"| {engine} | {_fmt_metric(stats['concordance'])} | "
                f"{_fmt_metric(stats['spearman'])} | {stats['contests']} |"
            )
        lines.append("")
    return lines


def _side_by_side_top(results):
    """Per-engine top-N leaderboard tables with full columns.

    A single side-by-side table with all four columns per engine becomes
    unreadable, so each engine gets its own ``display_name | org | rating |
    contests`` table laid out one after another.
    """
    engines = list(results)
    lines = [f"## Top {COMPARE_TOP} leaderboards (full columns)\n"]
    for engine in engines:
        board = results[engine]["leaderboard"]
        lines.append(f"### {engine}\n")
        lines.append("| # | Player | Org | Rating | Contests |")
        lines.append("|---|--------|-----|--------|----------|")
        for idx in range(min(COMPARE_TOP, len(board))):
            player = board[idx]
            lines.append(
                f"| {idx + 1} | {player.display_name} | {player.org} | "
                f"{_round(player.rating)} | {player.contests} |"
            )
        lines.append("")
    return lines


def _overlap_section(results):
    """Top-100 key overlap for every engine pair.

    With exactly two engines this is one A-B line (the historical behaviour);
    with three or more it emits one line per unordered pair so each pairwise
    overlap is reported.
    """
    engines = list(results)
    lines = [f"## Top {OVERLAP_TOP} overlap\n"]
    if len(engines) < 2:
        lines.append("_Need at least two engines to compute overlap._\n")
        return lines
    top_keys = {
        name: {p.key for p in results[name]["leaderboard"][:OVERLAP_TOP]}
        for name in engines
    }
    for i in range(len(engines)):
        for j in range(i + 1, len(engines)):
            a, b = engines[i], engines[j]
            common = top_keys[a] & top_keys[b]
            lines.append(
                f"Shared players in top {OVERLAP_TOP} between **{a}** and "
                f"**{b}**: **{len(common)}** / {OVERLAP_TOP}\n"
            )
    return lines


def _run_summary(results, context):
    """Opening run-summary block: data scale + per-engine key stats.

    ``context`` (optional) carries cli-measured values that the engines and
    metrics do not retain: data-scale counts and per-engine wall-clock timing.
    Missing values degrade gracefully to "n/a".
    """
    lines = ["## 运行摘要\n"]
    ctx = context or {}

    lines.append("### 数据规模\n")
    lines.append("| 指标 | 数值 |")
    lines.append("|------|------|")
    lines.append(f"| 计入场次 (loaded) | {ctx.get('loaded', 'n/a')} |")
    # Coverage-gate skips and same-venue dedup are distinct reasons; report them
    # on separate lines so the dedup count is not miscounted as low-coverage.
    # ``skipped_coverage``/``skipped_dedup`` are the bucketed values the cli
    # supplies; fall back to the legacy combined ``skipped`` for the first line.
    coverage_skipped = ctx.get("skipped_coverage", ctx.get("skipped", "n/a"))
    dedup_skipped = ctx.get("skipped_dedup", "n/a")
    lines.append(f"| 跳过场次 (coverage < 阈值) | {coverage_skipped} |")
    lines.append(f"| 同场去重 | {dedup_skipped} |")
    lines.append(f"| 加载告警 (warnings) | {ctx.get('warnings', 'n/a')} |")
    by_cat = ctx.get("loaded_by_category") or {}
    if by_cat:
        cat_str = ", ".join(f"{k}={v}" for k, v in sorted(by_cat.items()))
        lines.append(f"| 计入场次分类 | {cat_str} |")
    span = ctx.get("year_span")
    if span:
        lines.append(f"| 年份跨度 | {span[0]}–{span[1]} |")
    lines.append(f"| unique 选手数 (>=1 场) | {ctx.get('unique_players', 'n/a')} |")
    lines.append(
        f"| 有 >=3 场的选手数 | {ctx.get('players_min_contests', 'n/a')} |"
    )
    lines.append("")

    lines.append("### 各引擎运行\n")
    lines.append("| 引擎 | 回测耗时(s) | 计入场次 | 上榜选手(>=3) | overall concordance | overall spearman |")
    lines.append("|------|-------------|----------|----------------|---------------------|------------------|")
    timings = ctx.get("timings") or {}
    for engine in results:
        overall = results[engine]["metrics"]["overall"]
        board = results[engine]["leaderboard"]
        secs = timings.get(engine)
        secs_str = f"{secs:.2f}" if isinstance(secs, (int, float)) else "n/a"
        lines.append(
            f"| {engine} | {secs_str} | {overall['contests']} | {len(board)} | "
            f"{_fmt_metric(overall['concordance'])} | "
            f"{_fmt_metric(overall['spearman'])} |"
        )
    lines.append("")
    return lines


def _sanity_check(context):
    """Common-sense (sanity) block sourced from cli-supplied findings.

    ``context['sanity']`` is a list of pre-rendered markdown lines (the cli
    builds it from the actual leaderboards). When absent, emit a short notice.
    """
    lines = ["## 常识校验\n"]
    sanity = (context or {}).get("sanity")
    if not sanity:
        lines.append("_未提供常识校验数据。_\n")
        return lines
    lines += sanity
    lines.append("")
    return lines


def _final_config_summary():
    """Config summary, sourced live from the incremental engine.

    Generated (not hand-edited) so the recorded parameters can never drift from
    the code: every number is read live from
    :mod:`xcpc_rating.engines.incremental` and :mod:`xcpc_rating.tier`, the single
    source of truth. Documents the admission rule, the ladder step/newcomer
    parameters, the per-tier eligibility gates and field floors, and the Final
    mean-injection. Earlier revisions documented a three-engine μ/σ pipeline;
    those engines were removed -- only the incremental ladder remains.
    """
    from .engines import incremental as c
    from .engines.incremental import IncrementalEngine
    from . import tier

    weights = tier.TIER_WEIGHTS
    gates = c.TIER_GATES
    floors = c.TIER_FIELD_FLOOR
    injection = getattr(IncrementalEngine(), "final_avg_injection", None)

    def _v(value):
        """Render a gate/floor value, or 无 (none) for an absent threshold."""
        return f"{value:g}" if value is not None else "无"

    lines = ["## 最终配置汇总（冻结生产配置）\n"]
    lines.append("| 维度 | 取值 | 说明 |")
    lines.append("|------|------|------|")
    lines.append(
        "| 准入 | 有名单即计分（min_coverage=0.0） | 任一有花名册的榜单计入，"
        "无名单榜单始终剔除 |"
    )
    lines.append(
        f"| 记分引擎 | incremental（阶梯） | 人人从 E={c.INITIAL_EXPECT:g} 起步，"
        "逐场 E += K·权重·(表现分 − E)，展示分从 0 爬升 |"
    )
    lines.append(
        f"| 表现分 | CF 纯口径（几何均值反解） | "
        f"冠军额外 self-excluded top-{c.CHAMP_TOPK} 锚点 solve |"
    )
    lines.append(
        f"| 步长 K | 基础 {c.K_BASE:g} / 新秀提速 ×{c.EARLY_BOOST:g}"
        f"（衰减 {c.EARLY_FADE:g}）/ 上限 {c.K_MAX:g} | "
        "少场次精英更快收敛 |"
    )
    lines.append(
        f"| 新秀展示偏移 | {c.NEWCOMER_OFFSET:g}·{c.NEWCOMER_FADE:g}^n | "
        "展示分 = max(0, E − 偏移)，约 3-4 场收敛到 E |"
    )
    lines.append(
        f"| 层级系数 | final {weights[tier.TIER_FINAL]:g} / "
        f"regional {weights[tier.TIER_REGIONAL]:g} / "
        f"invitational {weights[tier.TIER_INVITATIONAL]:g} / "
        f"provincial {weights[tier.TIER_PROVINCIAL]:g} | 每场步长权重乘子 |"
    )
    lines.append(
        f"| 计分门槛 gate | 省赛 E<{_v(gates['provincial'])} / "
        f"邀请赛 E<{_v(gates['invitational'])} / "
        f"区域赛 {_v(gates['regional'])} / final {_v(gates['final'])} | "
        "高于门槛的强队完全 unrated，不进记分场 |"
    )
    lines.append(
        f"| 场强地板 field floor | 区域赛 {_v(floors['regional'])} / "
        f"邀请赛 {_v(floors['invitational'])} / "
        f"省赛 {_v(floors['provincial'])} / final {_v(floors['final'])} | "
        "弱尾队伍强度抬升至地板后再反解表现分，拉开区域赛/邀请赛区分度 |"
    )
    lines.append(
        f"| Final 均值注入 | 全员步长平移使本场平均变化 ≈ 人数×{_v(injection)} | "
        "保证打 Final 的整体上分 |"
    )
    lines.append("")
    lines.append(
        "> 语义：人人从 0 起步、逐场累积的阶梯分。低于预期不涨分（达预期不扣分），"
        "整体偏通缩；省赛/邀请赛设 gate 与 field floor 拉开层级区分度。\n"
    )
    return lines


def write_comparison(results, out_dir, context=None):
    """Write ``comparison.md`` summarizing metrics and leaderboards.

    ``results`` maps engine_name -> {"metrics": <replay summary>,
    "leaderboard": [PlayerRating, ...]}. ``context`` is an optional dict of
    cli-measured run statistics and sanity findings. Returns the output path.
    """
    _ensure_dir(out_dir)
    lines = ["# Engine comparison\n"]
    lines += _run_summary(results, context)
    lines += _final_config_summary()
    lines += _metrics_table(results)
    lines += _side_by_side_top(results)
    lines += _overlap_section(results)
    lines += _sanity_check(context)

    path = os.path.join(out_dir, "comparison.md")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))
    return path
