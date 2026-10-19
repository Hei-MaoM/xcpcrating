# Data Structure Visualization

## Current (Before Phase 2)
```
web/public/data/
├── skill-leaderboards/
│   ├── index.json                           (101 MB - monolithic!)
│   ├── all/overall/
│   │   ├── adhoc.json                       (4.4 MB)
│   │   ├── technique.json                   (4.4 MB)
│   │   ├── dp.json                          (4.4 MB)
│   │   └── ... (10 more axes)
│   └── official/overall/
│       ├── adhoc.json                       (4.2 MB)
│       └── ... (12 more axes)
├── period-index.json                        (8.1 MB - needs Phase 2 future work)
└── search/players/
    ├── 00.json                              (varying sizes)
    ├── b5.json                              (400 KB - largest!)
    └── ... (254 more shards)
```

## After Phase 2 & 3
```
web/public/data/
├── skill-leaderboards/
│   ├── index.json                           (101 MB - kept for compatibility)
│   ├── all/overall/
│   │   ├── adhoc.json                       (4.4 MB - kept for compatibility)
│   │   ├── adhoc/                           ⭐ NEW PAGINATED
│   │   │   ├── meta.json                    (0.5 KB)
│   │   │   ├── page-1.json                  (50-100 KB, 100 players)
│   │   │   ├── page-2.json                  (50-100 KB)
│   │   │   ├── page-3.json                  (50-100 KB)
│   │   │   └── ... (total ~40 pages)
│   │   ├── technique/                       ⭐ NEW PAGINATED
│   │   │   ├── meta.json
│   │   │   ├── page-1.json
│   │   │   └── ...
│   │   └── ... (11 more paginated axes)
│   └── official/overall/
│       ├── adhoc/                           ⭐ NEW PAGINATED
│       │   └── ... (same structure)
│       └── ... (12 more paginated axes)
│
├── search-index/
│   ├── popular-names.json                   (50 KB - Phase 1)
│   └── trie-meta.json                       ⭐ NEW (100-200 KB)
│       └── Contains: root node + common prefixes
│
├── period-index.json                        (8.1 MB - future optimization)
└── search/players/                          (kept for compatibility)
    └── ... (256 shards)
```

## Data Flow Comparison

### Before (Monolithic):
```
User opens skill board
  ↓
Worker loads adhoc.json (4.4 MB)                 [10+ seconds]
  ↓
Parse & decode entire file                       [5+ seconds]
  ↓
Filter & paginate in memory
  ↓
Display page 1 (30 players)

Total: ~15 seconds, 200+ MB memory
```

### After Phase 2 (Paginated):
```
User opens skill board
  ↓
Worker loads adhoc/meta.json (0.5 KB)           [<50ms]
  ↓
Worker loads adhoc/page-1.json (50-100 KB)      [<500ms]
  ↓
Decode 100 players                              [<100ms]
  ↓
Display page 1 (30 players)

Total: <1 second, <10 MB memory
```

### Search Flow Comparison

#### Before (MD5 Shard):
```
User types "liming" (pinyin)
  ↓
Load shard for 'l' (~200 KB)                    [200ms]
  ↓
No direct match found
  ↓
Fallback: Load ALL 256 shards (9 MB total)      [2-5 seconds!]
  ↓
Scan each shard for pinyin match
  ↓
Return top 6 results

Total: 2-5 seconds
```

#### After Phase 3 (Trie):
```
User types "liming"
  ↓
Load trie-meta.json (cached, ~200 KB)           [<50ms on first use]
  ↓
Walk Trie: l → i → m → i → n → g
  ↓
Return inline cached results (up to 20)
  ↓
Display top 6 matches

Total: <150ms
```

## File Count Summary

| Category | Before | After Phase 2 | Difference |
|----------|--------|---------------|------------|
| Skill axis files | 26 | 26 (compat) | No change |
| Paginated dirs | 0 | 26 | +26 |
| Paginated pages | 0 | ~1000+ | +1000+ |
| Search shards | 256 | 256 (compat) | No change |
| Trie index | 0 | 1 | +1 |
| **Total data size** | **~150 MB** | **~150 MB** | Same* |

*Total size same, but load-on-demand reduces actual transfer by 90%+

## Bandwidth Savings Per User Session

### Typical User Session:
1. Opens site → Loads home page
2. Views skill board (1 axis) → **Before: 4.4 MB** → **After: 100 KB** (96% reduction)
3. Switches to another axis → **Before: 4.4 MB** → **After: 100 KB** (96% reduction)
4. Searches for player → **Before: 400 KB** → **After: 0 KB** (cached) or <50 KB Trie
5. Views player page → Same (no change)

**Total session bandwidth**:
- Before: 9+ MB
- After: 200-300 KB
- **Savings: 96%**

## Browser Memory Footprint

### Before:
- Skill board: 200+ MB (full board in memory)
- Search cache: 50+ MB (multiple shards)
- **Total: 250+ MB**

### After:
- Skill board: 10-20 MB (only loaded pages)
- Search Trie: 10 MB (one-time)
- Page LRU cache: <5 MB (max 10 pages)
- **Total: 25-35 MB** (90% reduction)
