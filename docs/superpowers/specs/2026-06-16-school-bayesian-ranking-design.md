# 学校排名（校排 → 表现分 → 贝叶斯零和更新）— 设计 spec

日期：2026-06-16 · 状态：已与用户确认设计，待实现

## 目标

新增「学校榜」功能：把每一所学校当作一个长期竞争主体，**每场比赛先对学校排名，再用 TrueSkill
式纯排名贝叶斯规则在线更新每所学校的技能信念**，最终按保守显示分给学校排名。这是一个独立于选手
评分引擎的**学校评分引擎**，不是对当前选手分的静态聚合。

## 一、每场比赛 → 学校名次

- 一所学校在某场比赛里只用它**最强的一支正式队伍**代表：取该校在该场所有 `official=true` 队伍
  中名次最靠前（rank 最小）的那一支，作为该校的本场名次。
- 把该场所有「有正式队伍参赛」的学校，按各自的代表名次升序排成一个名次序列，作为本场多人比赛的
  排名输入。两所学校代表名次相同 → 记为**平局（draw）**。
- 比赛集合与口径与选手「正式参赛」榜保持一致：
  - 复用 `loader.load_contests`（去重、覆盖率过滤后的赛事）。
  - 仅 `official=true` 队伍参与；非正式（打星）队伍不计入学校代表名次。
  - 跳过 `incremental.UNRATED_CONTESTS`（leaked-problem 等被判 void 的场次）。
  - 不设选手榜的资格 gate（gate 是按队伍强度决定选手分是否计入，对学校不适用）。
- 一场里只有 1 所学校参赛 → 无可比较对象，不更新（或仅做 τ 时间漂移，见下）。

## 二、记分（学校排名 → 表现分 → 贝叶斯零和更新）

> **方法演进（多次修正，按用户反馈）**：① Weng–Lin/TrueSkill 纯排名（相邻配对）——中游 μ 塌缩到
> ~1500、按场次排，不对。② 表现分 + 贝叶斯后验均值——被一支独强/几场高光拉高。③ 贝叶斯"可靠水平"
> `θ−Kψ`——但收敛项让人人往上爬、连偏差的一场也 +0.4，**不是零和**。④ 零和增量阶梯（固定 K=0.4）——
> 零和了但**像选手榜一样太 swingy**，被最近/极端的一场带跑。⑤ **最终**：贝叶斯**零和**——递减学习率
> （场次越多单场影响越小，稳健不 swingy）+ 零和位移（全场涨跌相抵）。

- **学校在该场的名次**：参赛学校按各自代表名次（最强队 rank）做 1224 排名 → "学校间名次"。
- **本场表现分**：参赛学校当作一个场（field，场强=各校当前评分），连同学校间名次喂给共享 CF 式求解器
  `perf.compute_performances(field, ranks)` → 每校本场表现分（压制越强越深的场分越高，带量级）。
- **表现分封顶（弱场不虚高）**：`cap_performances` 把每校表现分封在「**场内最强的其他学校 + `PERF_CAP_MARGIN=200`**」
  以内，再按名次做单调约束（不倒挂）。否则两所强校在弱省赛里 1-2 会被 cf 的"第1 vs 第2"硬生生拉开很多
  （实测四川省赛 电子科技 vs 四川 由 127 收到 55）；打弱场本就证明不了比对手高太多。强场里 cap 基本不触发。
- **贝叶斯零和更新**：每校维护评分 `R`（初始 `MU₀=1500`）、场次 `n`。每场：
  - 递减学习率 `α_i = 1/(KAPPA + n_i)`（含本场；`KAPPA=4`）——这是正态均值的在线后验更新，**场次越多
    α 越小、单场影响越小**，所以对极端的一场稳健、不被最近一场带跑。
  - **赛事权重** `w = SCHOOL_TIER_WEIGHTS[classify_tier(contest)]`：Final（EC/World/CCPC 总决赛，
    id `...ecfinal` / 标题「总决赛」）`1.5`、区域赛 `1.0`（基准）、邀请赛 `0.8`、省赛 `0.5`。越高规格推得越远。
  - `step_i = w·α_i·(perf_i − R_i)`；**零和位移** `inc = −mean(step)`；`R_i += step_i + inc`。
  - 全场 `Σ(step+inc)=0`（严格零和，无通胀）。打得高于自身评分 → 涨，低于 → 跌；老牌校动得很小，新校适应快。
- 表现分用**赛前**评分（无 look-ahead）；一场不足 2 校则跳过。

## 三、显示分与排名

- 显示分 = 评分 `R`，与选手榜同源的 **~1400–3000** 尺度，零和使全场均值恒为 `MU₀=1500`，按 R 降序排名。
- **实测**：区间约 **1301 ~ 2280**（北大 2280 > 清华 2235 > 浙大 2149 > 上交 2069 > 杭电 2013 > 中山 …）。
  关键性质：**严格零和**（单场 Σ变化 ≈ 1e-11）；**稳健**——成熟校单场仅微动（复旦深圳 34/192 → −0.1，
  而非阶梯的 −133），偏差的一场会**小幅下跌**（不再像可靠水平那样还 +0.4）；早期场次动得多（合理）。
- **已知数据局限**:org 名未做中英/别名归一,同一所学校的中英文名(如「北京大学」vs「Peking University」)
  会各自成行、场次被拆分。org 归一是更大的独立任务,暂不在本功能内。
- 与现有三个榜一致：**显示分四舍五入取整 + 同分并列名次（1224）**，复用 `web/src/lib/rank.ts` 的 `tiedRanks`。
- 排序：按 `rating` 降序（同分时学校名做稳定 tiebreak）。

## 四、数据流与文件

**后端**
- `src/xcpc_rating/engines/school.py`：`SchoolEngine`
  - 内部状态：`{org: {"rating", "contests"}}`。
  - `school_standings(contest)` / `rank_among_schools(best_ranks)`：最强队名次 / 1224 学校间名次。
  - `score_contest`：聚合 → 学校间名次 → `perf.compute_performances(场强R, 名次)` → 递减学习率
    `α=1/(KAPPA+n)` 的零和更新 `R += α(perf−R) + inc`，返回逐场 `SchoolResult`。
  - `rating(org)=R`；`prior_rating()=MU0`；`leaderboard()` 按 rating 降序。
- `export_web.py`：`replay_schools` 跑引擎（跳过 `UNRATED_CONTESTS`）→ `build_schools` → 写 `schools.json`
  （`{org, rating, contests}`）；并收集逐场 `学校成绩` 写 `school-history/<shard>.json`（按 md5(org) 分片）。
  逐场行含 `{slug,title,startAt,teamRank,teamCount,schoolRank,schoolCount,perf,delta}`，`delta` 为该场零和变化。

**前端**
- `web/src/lib/data.ts`：`SchoolRow` + `SchoolResultRow` + `getSchools()` / `getSchoolHistory(org)`。
- 路由 `/schools` 列表页 + `/school/:org` 详情页（`App.tsx`）+ 导航第 2 项「学校」（`TopBar.tsx`）。
- `SchoolsPage.tsx`：列 名次/学校/评分/场次，`formatScoreInt` + `tiedRanks`，学校名搜索；**点行 → `/school/:org`**。
- `SchoolPage.tsx`：页头（学校榜名次/评分/场次/最佳校排）+ **学校成绩**逐场表（比赛/日期/校排（最强队）/表现分/变化）；`key={org}` 重挂载重置。
- `SearchBox.tsx`：全局搜索纳入学校（学校优先、带「学校 · 评分 · 场次」标签）→ `/school/:org`。

## 五、范围与非目标

- 不做学校历史曲线（已有逐场 学校成绩 表）。
- 不改动选手评分引擎与现有三个榜。
- 学校榜仅「正式参赛」一个口径（用户已选）。

## 六、测试（`tests/test_school.py`）

- `rank_among_schools`：1224 并列、顺序对齐。
- `school_standings`：多队取最小 rank；非正式/未参赛/空 org/无名册队伍排除。
- `SchoolEngine`：`prior_rating==MU0`；**单场变化和为 0**（零和）；赢家涨/输家跌且相抵；**压制更大的场分涨更多**；
  单校比赛跳过；leaderboard 排序 + `min_contests` 过滤。
- 前端：`SchoolsPage` 整数显示 + 并列名次（复用已测的 `tiedRanks`）。

## 七、可调常量（school.py 顶部）

`MU0 = 1500.0`（= `perf.INITIAL_RATING`，零和使全场均值恒为此值）、`KAPPA = 4.0`（先验伪场次：定首场学习率
`1/(KAPPA+1)` 与稳定速度，越大越稳、越向 MU0 收）、`PERF_CAP_MARGIN = 200.0`（表现分封顶余量：最多比场内
最强其他学校高这么多；越小越压平弱场头部、越大越接近原始 cf）、`SCHOOL_TIER_WEIGHTS`（赛事权重：
`final=1.5`、`regional=1.0`、`invitational=0.8`、`provincial=0.5`）。
