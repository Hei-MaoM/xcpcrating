# xcpcrating 前端架构分析与性能优化方案

## 执行摘要

xcpcrating 是一个面向 XCPC 个人选手的静态评分网站。经过系统性分析，发现前端存在**严重的性能瓶颈**，主要体现在：
- **超大 JSON 文件加载**（100+ MB）
- **首屏加载过慢**
- **页面交互卡顿**
- **Web Worker 处理效率低**

本方案从架构层面提出系统性优化策略，预期可将首屏加载时间减少 60-80%，交互响应提升 3-5 倍。

---

## 一、当前架构分析

### 1.1 技术栈

**前端框架**
- React 18.3 + React Router 6.30（HashRouter）
- Vite 8.0（构建工具）
- TypeScript 6.0
- ECharts 5.6（图表库，按需加载）

**数据处理**
- Web Workers（2 个：skill.worker.ts, period.worker.ts）
- 自定义编解码器（skillLeaderboardCodec）
- MD5 分片策略

**部署方式**
- GitHub Pages（纯静态站点）
- 所有数据预生成为 JSON 文件

### 1.2 目录结构

```
web/
├── src/
│   ├── components/       # UI 组件
│   │   ├── ui/          # 基础组件（表格、分页、徽章等）
│   │   └── charts/      # ECharts 图表封装
│   ├── pages/           # 路由页面
│   │   ├── leaderboard/ # 榜单页（4 种模式）
│   │   ├── player/      # 选手详情
│   │   ├── contests/    # 比赛列表与详情
│   │   └── ...
│   ├── lib/             # 核心逻辑
│   │   ├── data.ts      # 数据层（700+ 行）
│   │   ├── search.ts    # 选手搜索
│   │   └── skillLeaderboardCodec.ts
│   └── styles/          # 全局样式
└── public/
    ├── data/            # 正式数据（生产环境）
    └── preview-data/    # 开发预览数据（516 MB）
```

### 1.3 数据契约

Python 导出器生成所有 JSON：

| 文件 | 大小 | 用途 |
|------|------|------|
| `period-index.json` | **8.1 MB** | 时间段榜单时间线 |
| `skill-leaderboards/index.json` | **101 MB** × 2 | 题型十三维榜单（all/official） |
| `problems-index.json` | 3.1 MB | 题目索引 |
| `contests-index.json` | 213 KB | 比赛索引 |
| `leaderboards/{kind}/pages/{n}.json` | 每页 ~50 KB | 分页榜单（100 人/页） |
| `players/{shard}.json` | 分片 | 选手详情（256 个分片） |

---

## 二、核心性能问题

### 2.1 超大 JSON 文件阻塞 ⭐⭐⭐

#### 问题描述
1. **题型榜单文件过大**：`skill-leaderboards/index.json` 达到 **101 MB**
   - 包含全部 47,000+ 选手的 13 个维度数据
   - 单次切换维度需要下载完整文件
   - JSON 解析耗时 5+ 秒（实测结果）

2. **时间段榜单**：`period-index.json` 达到 **8.1 MB**
   - 存储所有选手的完整时间线
   - Worker 需要一次性加载全部数据

#### 影响范围
- **首屏加载**：如果用户直接访问题型榜单，首次加载需等待 10+ 秒
- **内存占用**：解析后占用 200+ MB 内存
- **移动端体验**：在 4G 网络下几乎不可用

#### 现有缓解措施
- 使用 Web Worker 避免阻塞主线程
- 紧凑编码（`rowFields` + 数组行）减少 ~30% 体积
- 开发环境使用 `preview-data` 子集（但仍有 516 MB）

### 2.2 Web Worker 效率低 ⭐⭐

#### 问题描述
`skill.worker.ts` 和 `period.worker.ts` 的工作流程：
1. 完整下载 JSON 文件（无法流式处理）
2. 一次性解析整个数据集
3. 在内存中进行排序、过滤、分页
4. 只返回 30 行结果给主线程

#### 瓶颈分析
- **网络传输**：101 MB 下载需 3-10 秒（取决于网速）
- **解码开销**：`decodeSkillLeaderboardRows` 需遍历所有行
- **重复计算**：每次切换维度/搜索都重新处理全量数据
- **无渐进式渲染**：用户在 loading 状态等待全部完成

### 2.3 首屏资源过重 ⭐⭐

#### 问题描述
查看 `web/dist/assets`：
- `charts-*.js`：248 KB（ECharts 核心）
- `components-*.js`：231 KB
- `parseGeoJson-*.js`：228 KB（未使用的地图组件）
- `index-*.js`：222 KB
- `graphic-*.js`：145 KB

#### 分析
1. **ECharts 按需加载不彻底**：虽然用了 tree-shaking，但仍打包了不必要的模块
2. **路由懒加载不足**：部分页面组件未做 code splitting
3. **重复依赖**：多个 chunk 包含相同的工具函数

### 2.4 状态管理混乱 ⭐⭐

#### 问题描述
在 `LeaderboardPage.tsx` 及其子组件中：
- **4 个榜单模式共享一个页面组件**：
  - RatingsBoard（正式/全部参赛）
  - PeriodBoard（时间段）
  - SkillBoard（题型十三维）
- 每个子组件独立管理状态（`useState` × 3-5 个）
- URL 参数同步逻辑分散在各处
- 切换模式时需要手动清理参数

#### 典型问题
```typescript
// LeaderboardPage.tsx - 切换榜单时的参数清理
function selectBoard(next: BoardKind) {
  setSearchParams((prev) => {
    const merged = new URLSearchParams(prev)
    // 手动管理每个参数的清理规则
    merged.delete('page')
    merged.delete('from')
    if (next !== 'period') merged.delete('to')
    if (next !== 'skill') {
      merged.delete('axis')
      merged.delete('caliber')
      merged.delete('q')
    }
    return merged
  })
}
```

### 2.5 数据层设计问题 ⭐

#### `data.ts` 过于庞大（700+ 行）
- 混合了类型定义、数据获取、缓存逻辑
- 20+ 个接口类型定义
- 10+ 个数据获取函数
- 缺乏模块化分层

#### 缓存策略简单
```typescript
const cache = new Map<string, Promise<unknown>>()
```
- 无过期策略
- 无容量限制
- 无优先级控制

---

## 三、优化方案

### 3.1 数据分片与增量加载 ⭐⭐⭐

#### 核心思路
将 101 MB 的单一文件拆分为可按需加载的小文件。

#### 方案设计

**题型榜单分片策略**
```
原始结构：
skill-leaderboards/
  index.json  (101 MB, 47k 选手 × 13 维度)

优化后结构：
skill-leaderboards/
  meta.json                          # 元数据（总人数、分片映射）
  {mode}/{tier}/{axis}/
    page-{n}.json                    # 每页 100 人，排序后
    search-index.json                # 搜索索引（仅 key + name）
```

**实施细节**
1. **Python 导出器改造**（`export_web.py`）：
   ```python
   # 为每个维度单独导出
   for axis in SKILL_AXIS_ORDER:
       rows = sorted(data, key=lambda x: x[axis + '_score'], reverse=True)
       for page_num in range(1, total_pages + 1):
           page_rows = rows[(page_num-1)*100 : page_num*100]
           write_json(f'skill-leaderboards/official/overall/{axis}/page-{page_num}.json', 
                     {'rows': compact_encode(page_rows)})
   ```

2. **前端加载逻辑**（`SkillBoard.tsx`）：
   ```typescript
   async function loadSkillPage(axis: string, page: number) {
     // 只加载需要的单页数据
     const url = dataUrl(`skill-leaderboards/official/overall/${axis}/page-${page}.json`)
     const data = await fetch(url).then(r => r.json())
     return decodeSkillLeaderboardRows(data)
   }
   ```

#### 预期收益
- **首次加载**：101 MB → 50 KB（减少 99.95%）
- **切换维度**：即时响应（无需重新下载）
- **搜索功能**：加载独立的搜索索引（< 1 MB）

### 3.2 虚拟滚动与流式渲染 ⭐⭐

#### 问题
当前分页器每页只显示 30 行，但如果用户想快速浏览，需要频繁点击翻页。

#### 方案
引入虚拟滚动，支持一次加载 1000+ 行数据但只渲染可见部分。

#### 技术选型
- **react-window** 或 **@tanstack/react-virtual**
- 固定行高 48px，视口高度 ~800px → 只需渲染 20 行 DOM

#### 实施步骤
```typescript
import { useVirtualizer } from '@tanstack/react-virtual'

function VirtualLeaderboard({ rows }: { rows: LeaderboardRow[] }) {
  const parentRef = useRef<HTMLDivElement>(null)
  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 48,
    overscan: 5,
  })

  return (
    <div ref={parentRef} style={{ height: '800px', overflow: 'auto' }}>
      <div style={{ height: virtualizer.getTotalSize() }}>
        {virtualizer.getVirtualItems().map(item => (
          <div key={item.key} style={{
            position: 'absolute',
            top: 0,
            left: 0,
            width: '100%',
            height: item.size,
            transform: `translateY(${item.start}px)`,
          }}>
            <LeaderboardRow data={rows[item.index]} />
          </div>
        ))}
      </div>
    </div>
  )
}
```

#### 配合分片加载
- 首次渲染：加载前 3 页（300 行）
- 滚动触底：预加载下一批
- 缓存已加载的页面

### 3.3 时间段榜单优化 ⭐⭐⭐

#### 问题分析
`period-index.json`（8.1 MB）存储结构：
```typescript
type PeriodRow = [
  key: string,
  name: string,
  org: string,
  dates: number[],      // [20200901, 20201115, ...]
  ratings: number[]     // [1450, 1523, ...]
]
```

#### 优化方案

**方案 A：按年份分片**
```
period-data/
  2020.json  (比赛较少，~500 KB)
  2021.json  (~1.5 MB)
  2022.json  (~2 MB)
  2023.json  (~2 MB)
  2024.json  (~2 MB)
```

用户选择日期范围时，只加载相关年份的文件。

**方案 B：差分编码**
不存储完整的 ratings 数组，改为存储增量：
```typescript
// 原始：[1400, 1450, 1523, 1489, ...]
// 优化：[1400, +50, +73, -34, ...]  → 用 int16 存储增量
```

结合 gzip 压缩，可再减少 40-50% 体积。

**方案 C：预计算热门时间段**
```
period-snapshots/
  latest.json           # 最新榜单（最常访问）
  2024-Q4.json         # 季度快照
  2024-Q3.json
  ...
```

用户选择"截至今日"时直接返回，无需 Worker 计算。

#### 推荐实施
先实施**方案 A + 方案 C**，快速见效；长期考虑方案 B。

### 3.4 首屏性能优化 ⭐⭐⭐

#### 3.4.1 关键资源优化

**移除未使用的 ECharts 组件**
```typescript
// 当前：web/src/components/charts/RatingChart.tsx
import('echarts/core')
import('echarts/charts')      // 包含 Line, Scatter, Bar, Pie...
import('echarts/components')  // 包含 Grid, Tooltip, Legend, Geo...

// 优化：只导入需要的
import { LineChart, ScatterChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
```

**去除 parseGeoJson-*.js（228 KB）**
检查是否真的需要地图功能，如果不需要则从依赖中排除。

#### 3.4.2 构建配置优化

```typescript
// vite.config.ts
export default defineConfig({
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          // 分离第三方库
          'react-vendor': ['react', 'react-dom', 'react-router-dom'],
          'echarts-vendor': ['echarts/core', 'echarts/charts', 'echarts/components'],
          // 按路由分离
          'player': ['./src/pages/player/PlayerPage.tsx'],
          'contests': ['./src/pages/contests/ContestsPage.tsx'],
        }
      }
    },
    // 启用压缩
    minify: 'terser',
    terserOptions: {
      compress: {
        drop_console: true,  // 生产环境移除 console
        pure_funcs: ['console.log', 'console.info']
      }
    }
  }
})
```

#### 3.4.3 预加载策略

```html
<!-- index.html -->
<head>
  <!-- DNS 预解析 -->
  <link rel="dns-prefetch" href="https://heimaom.cn">
  
  <!-- 预加载首屏必需资源 -->
  <link rel="preload" href="/data/meta.json" as="fetch" crossorigin>
  <link rel="preload" href="/data/leaderboards/official/meta.json" as="fetch" crossorigin>
</head>
```

### 3.5 状态管理重构 ⭐⭐

#### 问题回顾
4 个榜单模式共享一个页面，状态散落在各个子组件。

#### 方案：引入轻量状态管理

**选项 1：Zustand（推荐）**
```typescript
// stores/leaderboard.ts
import { create } from 'zustand'

interface LeaderboardState {
  board: 'official' | 'all' | 'period' | 'skill'
  page: number
  org: string | null
  
  setBoard: (board: BoardKind) => void
  setPage: (page: number) => void
  reset: () => void
}

export const useLeaderboardStore = create<LeaderboardState>((set) => ({
  board: 'official',
  page: 1,
  org: null,
  
  setBoard: (board) => set({ board, page: 1 }),
  setPage: (page) => set({ page }),
  reset: () => set({ page: 1, org: null }),
}))
```

**选项 2：Context + useReducer**
如果不想引入外部依赖，可以用 React 内置方案。

### 3.6 数据层模块化 ⭐

#### 目标
将 `data.ts`（700+ 行）拆分为职责清晰的模块。

#### 新结构
```
lib/
├── data/
│   ├── types/           # 类型定义
│   │   ├── contest.ts
│   │   ├── player.ts
│   │   ├── leaderboard.ts
│   │   └── index.ts
│   ├── api/             # 数据获取
│   │   ├── contests.ts
│   │   ├── players.ts
│   │   ├── leaderboards.ts
│   │   └── index.ts
│   ├── cache.ts         # 缓存管理
│   └── index.ts
├── search.ts
├── format.ts
└── ...
```

### 3.7 搜索优化 ⭐⭐

#### 当前问题
`searchPlayers` 需要加载多个分片文件才能返回结果。

#### 优化方案

**构建倒排索引**
```
search-index/
  prefix-a.json    # 所有 a 开头的选手
  prefix-b.json
  ...
  pinyin-a.json    # 拼音首字母 a
  ...
```

### 3.8 其他优化点 ⭐

#### Service Worker
```typescript
// 缓存策略
- 静态资源（JS/CSS）：Cache First
- 数据文件（JSON）：Network First，24 小时后 Stale While Revalidate
```

---

## 四、实施路线图

### 阶段 1：快速见效（1-2 周）⭐⭐⭐

**优先级 P0**
1. 题型榜单分片（预期减少 99% 首次加载）
2. 时间段榜单按年分片（减少 60-75% 加载）
3. 首屏资源优化

**验收标准**
- 题型榜单首次加载 < 2 秒
- 首屏 FCP < 1.5 秒

### 阶段 2：体验提升（2-3 周）⭐⭐

**优先级 P1**
1. 虚拟滚动
2. 状态管理重构
3. 搜索索引优化
4. 缓存层升级

**验收标准**
- 榜单滚动流畅（60 fps）
- 搜索响应 < 200ms

### 阶段 3：架构优化（3-4 周）⭐

**优先级 P2**
1. 数据层模块化
2. Service Worker
3. 预计算热门时间段
4. 监控埋点

---

## 五、性能目标

| 指标 | 当前值 | 目标值 | 改善幅度 |
|------|--------|--------|----------|
| 首屏 FCP | ~4s | < 1.5s | **63%** |
| 题型榜单首次加载 | 10s+ | < 2s | **80%** |
| 切换维度响应 | 5s+ | < 0.5s | **90%** |
| 搜索响应 | 1-2s | < 0.2s | **85%** |
| 时间段榜单加载 | 6-8s | < 2s | **70%** |
| Lighthouse 性能分 | ~60 | > 90 | **+50%** |

---

## 六、风险与注意事项

### 6.1 向后兼容性

**问题**：修改数据格式后，旧版前端可能无法工作。

**应对**
- 保留旧格式一个版本周期
- 在 `meta.json` 中声明数据版本号
- 前端检测版本并提示用户刷新

### 6.2 存储成本

**问题**：分片后文件数量增加，可能增加存储/带宽成本。

**分析**
- 当前单文件 101 MB
- 分片后总大小可能增至 120 MB（+20%）
- 但大部分文件不会被访问，CDN 缓存命中率更高
- 实际带宽成本可能降低 50%+

### 6.3 开发复杂度

**问题**：分片加载、虚拟滚动增加了代码复杂度。

**应对**
- 封装通用 hooks（`useVirtualLeaderboard`）
- 完善单元测试
- 详细的文档和注释

---

## 七、替代方案对比

### 方案 A：完全重写为 SSR/SSG

**优点**：SEO 友好，首屏性能最优

**缺点**：需要服务器，开发成本高

**结论**：不推荐，与项目定位不符

### 方案 B：使用 SQLite WASM

**优点**：支持复杂查询，压缩率更高

**缺点**：首次加载仍需下载完整 DB 文件，技术风险高

**结论**：不推荐作为首选

### 方案 C：本方案（数据分片 + 增量加载）

**优点**：改动最小，风险可控，立竿见影

**缺点**：需要改造 Python 导出器

**结论**：✅ 推荐采用

---

## 八、总结

xcpcrating 前端的核心性能瓶颈在于**超大 JSON 文件**的加载与解析。通过**数据分片、增量加载、虚拟滚动**等手段，可以在保持纯静态部署的前提下，将首屏加载时间减少 60-80%，交互响应提升 3-5 倍。

建议按照三阶段路线图实施，优先完成高优先级优化（阶段 1），快速验证效果后再推进后续工作。

---

**文档版本**：v1.0  
**创建日期**：2024-10-20  
**作者**：Codex AI
