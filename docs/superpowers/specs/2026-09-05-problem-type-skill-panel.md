# 题型能力七维面板规格

## 目标

从 2024-01-01 起为选手生成按赛事档位分组的题型能力面板。2025 年优先作为第一批数据；题型由题面与题解分析得到，不把 QOJ tag 当作算法分类依据。

七个固定轴：

1. 数据结构
2. 图论与网络
3. 动态规划
4. 数学
5. 字符串
6. 几何
7. 基础算法

旧五维比赛表现面板保留，题型面板作为独立的七边形雷达。

## 题目分类

- 每题最多两个轴，默认主标签 0.7、次标签 0.3；确实不可拆分时允许 0.5/0.5。
- 按核心解法分类，而不是按题面出现的工具名分类。
- 线段树、Trie 等仅作为辅助实现时不单独抬高数据结构轴；树形 DP 以 DP 为主，几何构造以几何为主。
- 无法从题面或题解验证核心方法时标记 `unknown`，不平均摊到七个轴。
- manifest 保存题目身份、标签权重、置信度、证据摘要、题解/题面链接和规则版本。

来源优先级：官方 Tutorial/Editorial > QOJ 题面与 Editorial > 可核验的外部题解。正式分类使用两个独立高推理分析，冲突由第三次分析仲裁，并保留结果。

## 能力统计

每道题的难度权重优先由该赛事通过率平滑得到；同一选手、同一 mode、同一赛事档位内按 canonical problem id 去重。

对于轴 `d`：

```text
exposure_d = Σ(labelWeight × difficultyWeight)
success_d  = Σ(exposure × solved)
mastery_d  = (success_d + priorWeight × cohortPrior)
            / (exposure_d + priorWeight)
```

其中 `solved` 是队伍是否通过该题，不能解释为队内个人提交归因。payload 同时保存原始 success/exposure、唯一题数、有效场次、分类覆盖率和 unknown 量。

有已分类证据的轴即可参与百分位和等级；不再设置个人至少 3 题的硬门槛。展示分使用小样本收缩，排名分使用保守下界；有效题数和覆盖率作为样本提示。百分位在相同赛事档位和 mode 的选手 cohort 内计算。

单项等级：该轴第 1 名为 SSS，前 10 名为 SS，其余沿用 S–F 百分位档位。综合题型能力最多作为普通 S–F 参考，不覆盖单项 SSS/SS。

## 数据契约

新增独立题型 manifest，不把题解文本放入玩家 shard：

```json
{
  "version": "problem-types-v1",
  "sourceWindow": {"from": "2024-01-01"},
  "axes": [{"key": "dataStructure", "label": "数据结构"}],
  "problems": {
    "qoj:14801": {
      "contestKey": "icpc2025nanjing",
      "alias": "A",
      "labels": {"basic": 0.7, "math": 0.3},
      "confidence": 0.92,
      "status": "classified",
      "evidence": [{"kind": "editorial", "url": "...", "summary": "..."}]
    }
  }
}
```

玩家记录新增 `skillPanel[mode][tier]`，旧 `panel` 字段保持兼容。前端按 manifest 的轴顺序绘制七边形，并显示覆盖率、样本数和题目明细。

## 分阶段交付

1. 先建立 2023 年以来能匹配 QOJ 的赛事/题目 registry 和分类 manifest，优先有官方题解的主赛。
2. 用小规模导出验证难度权重、队伍 AC 映射、跨赛去重和七轴统计。
3. 增加后端单元测试、导出集成测试和前端七边形/兼容性测试。
4. 接入播放器页面并人工抽查；确认口径稳定后补齐 2024、2023。
