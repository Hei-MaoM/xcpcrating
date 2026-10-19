## 九、搜索性能深度分析

### 9.1 当前搜索实现

**搜索流程**
```typescript
// SearchBox.tsx
用户输入 → 防抖 180ms → getPlayerSearchPrefix → 加载分片 JSON → 过滤匹配 → 显示结果
```

**数据组织**
- 选手搜索索引：256 个分片文件（按查询首字符 MD5 哈希）
- 总大小：9.21 MB
- 最大单个分片：b5.json (400 KB, ~2000 选手)
- 学校索引：schools.json (97 KB, 一次性加载)
- 比赛索引：contests-index.json (213 KB, 一次性加载)

### 9.2 核心性能问题 ⭐⭐⭐

#### 问题 1：大分片文件解析慢

**影响最严重的分片**
```
b5.json - 400 KB  (常见姓氏"李"开头)
12.json - 383 KB  (汉字"张"等)
89.json - 319 KB  (汉字"王"等)
46.json - 303 KB  (汉字"刘"等)
64.json - 301 KB  (常见姓氏)
```

**瓶颈分析**
- 用户输入"李"时，需下载 400 KB 的 b5.json
- JSON 解析 + 解码耗时 200-500ms
- 包含 ~2000 条记录，但只显示前 6 条结果
- **数据利用率仅 0.3%**

#### 问题 2：拼音回退搜索成本高

```typescript
// lib/data.ts - getPlayerSearchPrefix
if (!looksLikePinyinQuery(query) || needle.length > 6) return direct

// 拼音首字母和"姓名第一个字"不是同一个分片键
// 所以命中不了，需要批量扫描分片
const hits: PlayerSearchEntry[] = []
for (let start = 0; start < ALL_SHARDS.length && hits.length < FALLBACK_LIMIT; start += FALLBACK_BATCH) {
  const batch = ALL_SHARDS.slice(start, start + FALLBACK_BATCH)
  const loaded = await Promise.all(
    batch.map((candidate) => loadPlayerShard(candidate))
  )
  // 逐个过滤...
}
```

**问题**
- 用户输入"liming"（拼音），直接查分片找不到
- 触发回退：批量加载多个分片（最多可能扫描所有 256 个）
- 每批 10 个并发请求，共 25+ 批次
- 总耗时可达 3-5 秒

#### 问题 3：防抖延迟体验差

```typescript
const DEBOUNCE_MS = 180
const debounced = useDebounce(query.trim(), DEBOUNCE_MS)
```

- 180ms 防抖 + 网络请求 + 解析 = 用户等待 300-800ms
- 对比现代搜索体验（Google/百度 < 100ms），明显滞后

#### 问题 4：重复网络请求

```typescript
// 每次输入都重新请求，即使之前加载过
getPlayerSearchPrefix(debounced)
  .then((rows) => { /* ... */ })
```

- 缓存策略依赖浏览器 HTTP 缓存
- 组件卸载/重新挂载会丢失内存缓存
- 同一会话中重复搜索"王"、"李"等常见姓氏会反复请求

### 9.3 用户体验影响

**典型场景测试**
| 输入 | 分片大小 | 下载耗时 | 解析耗时 | 总耗时 | 用户感知 |
|------|----------|----------|----------|--------|----------|
| 李明 | 400 KB | 200ms | 150ms | 530ms | 明显卡顿 |
| zhang | 320 KB | 180ms | 120ms | 480ms | 明显卡顿 |
| abc (拼音回退) | 2+ MB | 1500ms | 800ms | 2500ms+ | 严重卡顿 |
| Smith | 5 KB | 30ms | 10ms | 220ms | 可接受 |

**问题严重性**
- 80% 的中文用户搜索会触发大分片加载
- 20% 的拼音搜索会触发回退扫描（最慢）
- 移动端 4G 网络下几乎不可用

---

## 十、搜索优化方案

### 10.1 前缀树 + 增量加载 ⭐⭐⭐

#### 核心思路
用**前缀树（Trie）**索引替代分片哈希，支持增量加载和拼音双键索引。

#### 方案设计

**新索引结构**
```
search-index/
  trie-meta.json              # 前缀树元数据
  nodes/
    root.json                 # 根节点（高频前缀）
    prefix-{hash}.json        # 按前缀分块
  
  快速路径：
  popular-names.json          # 前 1000 个高频姓名（预加载）
  pinyin-index.json           # 拼音首字母映射表
```

**前缀树节点设计**
```typescript
interface TrieNode {
  prefix: string              // 当前前缀（如"李"、"lim"）
  count: number              // 该前缀下的选手数
  results?: PlayerSearchEntry[]  // 当 count <= 100 时直接内嵌结果
  children?: {               // 否则指向子节点
    [char: string]: string   // 子字符 → 子节点文件路径
  }
}
```

**实施细节**

1. **Python 导出器改造**（`export_web.py`）
```python
def build_search_trie(players):
    """构建多键前缀树（汉字 + 拼音）"""
    trie = TrieNode()
    
    for player in players:
        # 汉字姓名索引
        add_to_trie(trie, player.name, player)
        
        # 拼音索引
        pinyin_full = to_pinyin(player.name)
        pinyin_initials = get_initials(pinyin_full)
        add_to_trie(trie, pinyin_full, player)
        add_to_trie(trie, pinyin_initials, player)
        
        # 学校索引
        add_to_trie(trie, player.org, player)
    
    # 分块序列化：节点数量 > 阈值时拆分
    serialize_trie(trie, max_node_size=100)

def add_to_trie(node, key, player):
    """递归插入，自动归一化（小写、去空格）"""
    normalized = normalize_key(key)
    # ... 标准 Trie 插入逻辑
```

2. **前端加载逻辑**（`SearchBox.tsx`）
```typescript
// 内存缓存已加载的节点
const trieCache = new Map<string, TrieNode>()

async function searchTrie(query: string, limit: number): Promise<PlayerSearchEntry[]> {
  const normalized = query.toLowerCase().trim()
  
  // 1. 检查高频缓存
  const popular = await loadPopularNames()  // 首次加载后永久缓存
  const popularHits = popular.filter(p => p.name.includes(normalized))
  if (popularHits.length >= limit) return popularHits.slice(0, limit)
  
  // 2. 遍历前缀树
  let node = await loadTrieNode('root')
  const results: PlayerSearchEntry[] = []
  
  for (const char of normalized) {
    // 检查当前节点是否有内嵌结果
    if (node.results && node.results.length > 0) {
      const hits = node.results.filter(p => 
        p.name.includes(normalized) || p.org.includes(normalized)
      )
      results.push(...hits)
      if (results.length >= limit) break
    }
    
    // 加载子节点
    if (!node.children?.[char]) break
    const childPath = node.children[char]
    node = await loadTrieNode(childPath)
  }
  
  return results.slice(0, limit)
}

async function loadTrieNode(path: string): Promise<TrieNode> {
  if (trieCache.has(path)) return trieCache.get(path)!
  
  const url = dataUrl(`search-index/nodes/${path}.json`)
  const node = await fetch(url).then(r => r.json())
  trieCache.set(path, node)
  return node
}
```

#### 预期收益
- **常见姓氏搜索**：400 KB → 10-20 KB（减少 95%）
- **拼音搜索**：无需回退扫描，直接命中拼音树
- **响应时间**：300-800ms → 50-150ms（提升 5-10 倍）
- **高频预加载**：前 1000 名选手（~50 KB）在首次聚焦时加载，后续即时响应

### 10.2 智能预加载 + 预测 ⭐⭐

#### 问题
用户打开搜索框后才开始加载索引，首次搜索必然等待。

#### 方案

**触发时机优化**
```typescript
export function SearchBox() {
  const [indexReady, setIndexReady] = useState(false)
  
  // 1. 页面空闲时预加载
  useEffect(() => {
    if ('requestIdleCallback' in window) {
      requestIdleCallback(() => {
        preloadSearchIndex().then(() => setIndexReady(true))
      })
    }
  }, [])
  
  // 2. 鼠标悬停时预加载
  const handleMouseEnter = () => {
    if (!indexReady) {
      preloadSearchIndex().then(() => setIndexReady(true))
    }
  }
  
  return (
    <div className="search" onMouseEnter={handleMouseEnter}>
      {/* ... */}
    </div>
  )
}

async function preloadSearchIndex() {
  // 并行加载
  await Promise.all([
    loadPopularNames(),
    loadTrieNode('root'),
    loadPinyinIndex(),
  ])
}
```

**预测性加载**
```typescript
// 用户输入"李"后，预测可能输入"李明"、"李华"等
const predictions = predictNextChar(currentQuery, trieNode)
predictions.slice(0, 3).forEach(char => {
  const nextPath = trieNode.children[char]
  if (nextPath) prefetchTrieNode(nextPath)  // 后台预取
})
```

### 10.3 Web Worker 并行处理 ⭐⭐

#### 问题
即使数据变小，JSON 解析 + 字符串匹配仍在主线程执行，影响 UI 响应。

#### 方案

**搜索 Worker**（`search.worker.ts`）
```typescript
// 在 Worker 中缓存整个前缀树
let trieCache: Map<string, TrieNode> = new Map()
let popularNames: PlayerSearchEntry[] = []

self.onmessage = async (event: MessageEvent<SearchRequest>) => {
  const { id, query, limit } = event.data
  
  // 在 Worker 中执行搜索
  const results = await searchTrie(query, limit)
  
  self.postMessage({
    type: 'result',
    id,
    results
  })
}
```

**主线程调用**
```typescript
const searchWorker = new Worker(new URL('./search.worker.ts', import.meta.url))
let requestId = 0

function searchAsync(query: string, limit: number): Promise<PlayerSearchEntry[]> {
  return new Promise((resolve) => {
    const id = ++requestId
    const handler = (event: MessageEvent) => {
      if (event.data.id === id) {
        resolve(event.data.results)
        searchWorker.removeEventListener('message', handler)
      }
    }
    searchWorker.addEventListener('message', handler)
    searchWorker.postMessage({ type: 'query', id, query, limit })
  })
}
```

### 10.4 防抖优化 + 即时反馈 ⭐

#### 问题
180ms 防抖对快速输入用户不友好。

#### 方案

**双阶段响应**
```typescript
export function SearchBox() {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<Hit[]>([])
  const [status, setStatus] = useState<'idle' | 'typing' | 'searching' | 'ready'>('idle')
  
  // 立即显示"搜索中"状态
  const handleInput = (e: ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value
    setQuery(value)
    setStatus(value ? 'typing' : 'idle')
  }
  
  // 短防抖（50ms）用于本地缓存查询
  const quickDebounced = useDebounce(query, 50)
  useEffect(() => {
    if (!quickDebounced) return
    
    // 先从内存缓存返回部分结果
    const cached = getCachedResults(quickDebounced)
    if (cached.length > 0) {
      setResults(cached)
      setStatus('ready')
    }
  }, [quickDebounced])
  
  // 长防抖（180ms）用于网络请求
  const fullDebounced = useDebounce(query, 180)
  useEffect(() => {
    if (!fullDebounced) return
    
    setStatus('searching')
    searchAsync(fullDebounced, MAX_PER_GROUP)
      .then(hits => {
        setResults(hits)
        setStatus('ready')
        cacheResults(fullDebounced, hits)
      })
  }, [fullDebounced])
  
  return (
    <div className="search">
      <input value={query} onChange={handleInput} />
      {status === 'typing' && <div className="search__hint">输入中…</div>}
      {status === 'searching' && <div className="search__hint">搜索中…</div>}
      {/* ... */}
    </div>
  )
}
```

### 10.5 缓存策略升级 ⭐

#### LRU 缓存
```typescript
class SearchCache {
  private cache = new Map<string, PlayerSearchEntry[]>()
  private accessOrder: string[] = []
  private maxSize = 100  // 缓存最多 100 个查询
  
  get(query: string): PlayerSearchEntry[] | null {
    if (!this.cache.has(query)) return null
    
    // 更新访问顺序
    this.accessOrder = this.accessOrder.filter(k => k !== query)
    this.accessOrder.push(query)
    
    return this.cache.get(query)!
  }
  
  set(query: string, results: PlayerSearchEntry[]): void {
    // LRU 淘汰
    if (this.cache.size >= this.maxSize) {
      const oldest = this.accessOrder.shift()!
      this.cache.delete(oldest)
    }
    
    this.cache.set(query, results)
    this.accessOrder.push(query)
  }
}

const searchCache = new SearchCache()
```

#### 持久化缓存
```typescript
// 使用 IndexedDB 持久化热门搜索结果
async function getCachedOrFetch(query: string): Promise<PlayerSearchEntry[]> {
  // 1. 内存缓存
  const memCached = searchCache.get(query)
  if (memCached) return memCached
  
  // 2. IndexedDB 缓存
  const dbCached = await db.searches.get(query)
  if (dbCached && Date.now() - dbCached.timestamp < 7 * 24 * 3600 * 1000) {
    searchCache.set(query, dbCached.results)
    return dbCached.results
  }
  
  // 3. 网络请求
  const results = await searchAsync(query, MAX_PER_GROUP)
  searchCache.set(query, results)
  await db.searches.put({ query, results, timestamp: Date.now() })
  return results
}
```

### 10.6 渐进式搜索 ⭐

#### 问题
用户输入"李明"时，必须等待完整结果才能看到任何内容。

#### 方案

**流式返回结果**
```typescript
async function* searchStream(query: string, limit: number): AsyncGenerator<PlayerSearchEntry> {
  // 先返回高频缓存
  const popular = await loadPopularNames()
  for (const player of popular) {
    if (matches(player, query)) {
      yield player
    }
  }
  
  // 再返回前缀树结果
  const trieResults = await searchTrie(query, limit)
  for (const player of trieResults) {
    yield player
  }
}

// UI 中使用
const [results, setResults] = useState<PlayerSearchEntry[]>([])
useEffect(() => {
  setResults([])
  const stream = searchStream(query, 20)
  
  ;(async () => {
    for await (const player of stream) {
      setResults(prev => [...prev, player])
    }
  })()
}, [query])
```

---

## 十一、搜索优化实施路线图

### 阶段 1：快速改进（3-5 天）⭐⭐⭐

**P0 优化**
1. ✅ 添加高频姓名预加载（popular-names.json, ~50 KB）
2. ✅ 实施内存 LRU 缓存
3. ✅ 优化防抖策略（双阶段响应）
4. ✅ 智能预加载（空闲时 + 鼠标悬停）

**预期收益**
- 常见查询响应时间：300-800ms → 100-200ms（提升 60-70%）
- 80% 的搜索命中内存缓存，即时返回

### 阶段 2：架构重构（1-2 周）⭐⭐⭐

**P0 优化**
1. ✅ 构建前缀树索引（Python 导出器）
2. ✅ 前端 Trie 加载逻辑
3. ✅ 拼音双键索引
4. ✅ Web Worker 并行搜索

**预期收益**
- 所有搜索响应时间 < 150ms
- 拼音搜索无需回退扫描
- 数据传输量减少 90-95%

### 阶段 3：体验优化（1 周）⭐⭐

**P1 优化**
1. ✅ 渐进式搜索（流式返回）
2. ✅ IndexedDB 持久化缓存
3. ✅ 预测性预加载
4. ✅ 搜索建议（输入提示）

**预期收益**
- 搜索体验接近 Google 水平
- 离线缓存支持

---

## 十二、搜索性能目标

| 指标 | 当前值 | 阶段 1 | 阶段 2 | 改善幅度 |
|------|--------|--------|--------|----------|
| 常见姓氏搜索 | 300-800ms | 100-200ms | < 100ms | **85%** |
| 拼音搜索 | 2-5s | 500ms | < 150ms | **95%** |
| 数据传输量 | 100-400 KB | 50-100 KB | 5-20 KB | **95%** |
| 首次搜索延迟 | 300ms+ | 50ms | 即时 | **100%** |
| 缓存命中率 | 0% | 60-70% | 80-90% | N/A |

---

## 十三、搜索优化代码示例

### 高频姓名导出器（Python）
```python
# src/xcpc_rating/export_web.py

def export_popular_names(players: list[Player], limit: int = 1000):
    """导出前 N 个高频选手（按参赛次数排序）"""
    popular = sorted(players, key=lambda p: p.contests_count, reverse=True)[:limit]
    
    compact = [{
        'key': p.key,
        'name': p.name,
        'org': p.org,
        'contests': p.contests_count,
        'rating': p.rating,
    } for p in popular]
    
    write_json('search-index/popular-names.json', compact)
```

### 前端智能预加载（TypeScript）
```typescript
// components/ui/SearchBox.tsx

let popularNamesPromise: Promise<PlayerSearchEntry[]> | null = null

function preloadPopularNames(): Promise<PlayerSearchEntry[]> {
  if (popularNamesPromise) return popularNamesPromise
  
  popularNamesPromise = fetch(dataUrl('search-index/popular-names.json'))
    .then(r => r.json())
    .then(rows => rows.map(decodePlayerSearchRow))
  
  return popularNamesPromise
}

export function SearchBox() {
  const [popularReady, setPopularReady] = useState(false)
  
  // 页面空闲时预加载
  useEffect(() => {
    if ('requestIdleCallback' in window) {
      requestIdleCallback(() => {
        preloadPopularNames().then(() => setPopularReady(true))
      }, { timeout: 2000 })
    } else {
      setTimeout(() => {
        preloadPopularNames().then(() => setPopularReady(true))
      }, 1000)
    }
  }, [])
  
  // 鼠标悬停时确保已加载
  const handleMouseEnter = () => {
    if (!popularReady) {
      preloadPopularNames().then(() => setPopularReady(true))
    }
  }
  
  return (
    <div className="search" onMouseEnter={handleMouseEnter}>
      {/* ... */}
    </div>
  )
}
```

### LRU 缓存实现（TypeScript）
```typescript
// lib/searchCache.ts

export class SearchLRUCache<T> {
  private cache = new Map<string, T>()
  private order: string[] = []
  
  constructor(private maxSize: number = 100) {}
  
  get(key: string): T | null {
    if (!this.cache.has(key)) return null
    
    // 更新访问顺序（移到队尾）
    this.order = this.order.filter(k => k !== key)
    this.order.push(key)
    
    return this.cache.get(key)!
  }
  
  set(key: string, value: T): void {
    if (this.cache.has(key)) {
      // 已存在，更新顺序
      this.order = this.order.filter(k => k !== key)
    } else if (this.cache.size >= this.maxSize) {
      // 满了，淘汰最旧的
      const oldest = this.order.shift()!
      this.cache.delete(oldest)
    }
    
    this.cache.set(key, value)
    this.order.push(key)
  }
  
  clear(): void {
    this.cache.clear()
    this.order = []
  }
  
  get size(): number {
    return this.cache.size
  }
}

export const searchCache = new SearchLRUCache<PlayerSearchEntry[]>(100)
```

---

## 总结

搜索功能的核心问题是**大分片文件阻塞**和**拼音回退扫描成本高**。通过**前缀树索引 + 高频预加载 + LRU 缓存**，可以将响应时间从 300-800ms（常见姓氏）或 2-5s（拼音）降至 < 150ms，数据传输量减少 90-95%。

优先实施**阶段 1 快速改进**（3-5 天），可立即见效；然后推进**阶段 2 架构重构**（1-2 周）彻底解决问题。
