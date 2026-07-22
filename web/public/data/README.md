# 数据目录

本目录的 JSON 文件由 Python 导出器生成，**不要手工编辑**：

```bash
PYTHONPATH=src python3 -m xcpc_rating.export_web
```

导出器（`src/xcpc_rating/export_web.py`）是数据契约的唯一真实来源，字段名与前端
`src/lib/data.ts` 中的 TypeScript 类型严格对应。

## 文件清单

| 文件 | 内容 |
| --- | --- |
| `meta.json` | 生成时间、引擎名、计数 |
| `contests-index.json` | 比赛索引（列表页用） |
| `contests/<slug>.json` | 单场比赛详情；`slug` = 比赛 id 中 `/` 替换为 `__` |
| `players/<shard>.json` | 单分片选手详情；`shard` = `md5(key)` 前 2 位十六进制 |
| `search/players/<shard>.json` | 按查询首字符加载的选手搜索候选；`shard` = `md5(首字符)` 前 2 位 |
| `leaderboards/<kind>/meta.json` | 榜单总人数、页数、学校人数索引；`kind` 为 `all` / `official` |
| `leaderboards/<kind>/pages/<n>.json` | 每页 100 人；每行含预计算的全局名次 |
| `leaderboards/<kind>/schools/<shard>.json` | 学校哈希桶；选择学校时按需加载 |
| `period-index.json` | 正式参赛历史时间线；由 Web Worker 下载并计算时间段榜单 |
| `schools.json` | 学校评分榜 |
| `school-history/<shard>.json` | 学校逐场历史哈希桶 |
| `predictions-index.json` | 即将举行比赛的赛前预测索引 |
| `predictions/<slug>.json` | 正式队伍积分排序、分级奖牌排序与预计奖牌线数据 |

首页只预加载 `official/meta.json` 与 `official/pages/1.json`；全量榜单和全量选手
搜索索引不再进入首屏请求链路。
