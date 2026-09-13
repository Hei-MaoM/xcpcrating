# 题型能力七维面板实施计划

> 目标：在保留旧五维比赛表现的前提下，接入 2025 优先、2024-01-01 起的题型能力七维面板。

## 阶段 1：建立题目分类数据

- 固定七轴 key、中文名和分类边界。
- 建立 2025 contest registry，记录 SRK contest key、QOJ contest/problem id、题目别名、题面和官方题解链接。
- 由两个独立高推理代理阅读题面/题解初标，第三次分析仲裁冲突。
- 产出 `problem-types` manifest；每条记录包含标签权重、confidence、evidence、status 和版本。
- 对题解不足的题保留 `unknown`，不填猜测标签。

## 阶段 2：后端统计与导出

- 新增 manifest loader 和 schema 校验。
- 从 raw contest problem statistics 计算平滑难度权重。
- 从队伍 statuses 判断 solved，按 `(player, mode, tier, canonicalProblemId)` 去重。
- 计算 success/exposure/mastery、coverage、uniqueProblems、validContests 和 cohort percentile。
- 新增 `skillPanel` compact payload 与 `meta.json` 的 taxonomy/source-window 元数据；不改动旧 `panel` wire 格式。

## 阶段 3：前端展示

- 增加 skill panel decoder，兼容旧数据中字段缺失的情况。
- 新增七边形 radar geometry 和轴明细卡。
- 显示单项 SSS/SS、S–F、样本不足和分类覆盖率。
- 明确提示题目状态是队伍级数据，不代表队内个人提交归因。
- 旧五维雷达作为比赛表现概览保留。

## 阶段 4：验证

- Python：标签归一化、难度平滑、unknown/冲突、跨赛去重、official 过滤、样本阈值、百分位和 SSS/SS。
- Export fixture：至少两场 2025 赛事、重复 canonical id、alias-only 题目和部分缺失题型。
- TypeScript：七边形坐标、decoder、旧 payload 兼容、覆盖率和样本不足渲染。
- 运行 `pytest`、`npm test`、`npm run lint`、`npm run build` 和 `git diff --check`。

## 阶段 5：数据扩展

- 先发布 2025 试点并人工抽查题型与雷达形状。
- 口径确认后扩展至 2024，再扩展至 2023；每次更新 manifest version 和 source window。
