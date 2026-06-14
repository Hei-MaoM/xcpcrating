# 数据目录

本目录的 JSON 文件由 Python 导出器生成，**不要手工编辑**：

```bash
python -m xcpc_rating.export_web
```

导出器（`src/xcpc_rating/export_web.py`）是数据契约的唯一真实来源，字段名与前端
`src/lib/data.ts` 中的 TypeScript 类型严格对应。

## 文件清单

| 文件 | 内容 |
| --- | --- |
| `meta.json` | 生成时间、引擎名、计数 |
| `contests-index.json` | 比赛索引（列表页用） |
| `contests/<slug>.json` | 单场比赛详情；`slug` = 比赛 id 中 `/` 替换为 `__` |
| `players-index.json` | 全量选手索引，数组压缩 |
| `players/<shard>.json` | 单分片选手详情；`shard` = `md5(key)` 前 2 位十六进制 |
| `leaderboard.json` | 阶梯分榜（全部参赛），按分数降序 |
| `leaderboard_official.json` | 阶梯分榜（仅正式参赛） |

本仓库随附一份最小占位数据（仅 `meta.json`），用于在导出器产出真实数据前
让开发服务器可以启动。运行导出器后会被真实数据覆盖。
