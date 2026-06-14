# srk rating · 前端数据站

竞赛选手天梯与赛事数据的纯静态网页：成就榜（A / elo_cf）、实力榜（B / openskill）、
赛前预测（A/B 引擎可切换）、实际结果、选手表现分轨迹与逐场历史。

报刊风视觉：白底、Swiss 网格、衬线标题、tabular-nums 数字、单一强调色牛津蓝、奖牌金银铜
语义色，不使用任何 UI 组件库。

## 技术栈

- Vite + React 18 + TypeScript
- react-router-dom（HashRouter，GitHub Pages 免配置）
- ECharts（`echarts/core` 按需注册，禁止全量引入）
- Vitest（单元测试）

## 开发

```bash
cd web
npm install          # 首次
npm run dev          # 启动开发服务器（默认 http://localhost:5173）
```

## 构建

```bash
npm run build        # tsc 类型检查 + vite 生产构建，产物在 dist/
npm run preview      # 本地预览构建产物
```

构建产物为纯静态文件，`vite.config.ts` 设 `base: './'`，因此既可发布到 GitHub Pages，
也可用任意静态服务器托管：

```bash
cd dist && python -m http.server 8080
```

## 测试

```bash
npm run test         # 运行 vitest 单元测试
```

当前覆盖 `lib/md5` 的分片契约：MD5 实现与 Python 导出器的
`hashlib.md5(key.encode("utf-8")).hexdigest()[:2]` 必须逐字节一致，否则按分片加载选手数据
会静默 404。测试用 Python 生成的真实摘要做基准。

## 数据来源

所有数据由 Python 管线导出，**不要手工编辑** `public/data/`：

```bash
python -m xcpc_rating.export_web
```

导出器（`src/xcpc_rating/export_web.py`）是数据契约的唯一真实来源，字段名与
`src/lib/data.ts` 中的 TypeScript 类型严格对应。前端只消费数据、不参与计分。

数据文件清单见 `public/data/README.md`。关键约定：

- `slug` = 比赛 id 中 `/` 替换为 `__`
- `shard` = `md5(key)` 前 2 位十六进制（256 片）
- `predictedRank` = 各引擎赛前 `predict_scores` 降序名次（1-based，稳定排序，无泄漏）
- `players-index.json` 数组压缩为 `[key, name, org, contests, ratingA, ratingB]`，
  场次不足（< 3）时 `ratingB` 为 `null`

## 目录结构

```
src/
  main.tsx                       入口；按序引入 tokens → typography → global → ui 样式
  App.tsx                        HashRouter 路由表（scaffold 后冻结，页面 agent 不改）
  styles/
    tokens.css                   设计 token：oklch 色板、clamp 字号、间距、强调色、奖牌色
    typography.css               Noto Serif SC / Noto Sans SC 层级、tabular-nums
    global.css                   reset、focus-visible、reduced-motion、布局容器
  lib/
    data.ts                      数据契约 TS 类型 + 带缓存的 fetch 层
    md5.ts                       纯 TS MD5（分片路由，与 Python 一致）
    format.ts                    日期 / 分数 / 名次 / 罚时 / 偏差格式化
    useDebounce.ts               防抖 hook
  components/
    ui/                          共享组件（scaffold 所有，页面 agent 只 import 不改）
      TopBar / SearchBox / Tabs / DataTable / Badge / Pagination / EngineSwitch
    charts/
      RatingChart.tsx            表现分轨迹图（player 页 agent 所有）
  pages/
    leaderboard/                 榜单页（榜单 agent 所有）
    contests/                    比赛列表 + 详情（比赛 agent 所有）
    player/                      选手详情（选手 agent 所有）
```

## 路由

| 路径 | 页面 |
| --- | --- |
| `#/` | 榜单页（A 成就榜 / B 实力榜） |
| `#/contests` | 比赛列表 |
| `#/contest/:slug` | 比赛详情（结果 / 预测，引擎可切换） |
| `#/player/:key` | 选手详情（表现分轨迹 + 逐场历史） |

互链：榜单行 → 选手页；选手历史行 → 比赛页；比赛页成员 → 选手页；顶栏全局搜索即时过滤。
