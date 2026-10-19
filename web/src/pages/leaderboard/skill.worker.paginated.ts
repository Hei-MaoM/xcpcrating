/// <reference lib="webworker" />

import type { SkillAxisKey, PanelScope, SkillLeaderboardIndexRow } from '../../lib/data'
import type { SkillWorkerRequest, SkillWorkerResponse } from './skillWorkerProtocol'

/**
 * Phase 2: Paginated skill leaderboard worker.
 *
 * Instead of loading a 6 MB monolithic axis file, this worker loads:
 * 1. A small meta.json file (~500 bytes) with pagination info
 * 2. Only the requested page (~50-100 KB) of players
 *
 * This reduces initial load time from 10+ seconds to <2 seconds.
 */

const scope = self as DedicatedWorkerGlobalScope
let dataBase = 'data/'

interface PaginatedMeta {
  version: string
  mode: string
  tier: string
  axis: string
  totalPlayers: number
  totalPages: number
  pageSize: number
  rowFields: string[]
}

interface PaginatedPage {
  page: number
  rows: unknown[][]
}

// Cache for metadata (tiny files, keep them all)
const metaCache = new Map<string, PaginatedMeta>()

// Cache for recently loaded pages (LRU, max 10 pages ~1 MB total)
const pageCache = new Map<string, SkillLeaderboardIndexRow[]>()
const MAX_PAGE_CACHE = 10

function post(message: SkillWorkerResponse): void {
  scope.postMessage(message)
}

function cacheKey(mode: string, tier: string, axis: string): string {
  return `${mode}/${tier}/${axis}`
}

function pageKey(mode: string, tier: string, axis: string, page: number): string {
  return `${mode}/${tier}/${axis}/page-${page}`
}

async function loadMeta(
  mode: 'all' | 'official',
  tier: PanelScope,
  axis: SkillAxisKey,
): Promise<PaginatedMeta> {
  const key = cacheKey(mode, tier, axis)
  const cached = metaCache.get(key)
  if (cached) return cached

  const response = await fetch(
    `${dataBase}skill-leaderboards/${mode}/${tier}/${axis}/meta.json`
  )
  
  if (!response.ok) {
    // Fallback: try to load the old monolithic file
    throw new Error(`元数据加载失败（HTTP ${response.status}）`)
  }

  const meta = (await response.json()) as PaginatedMeta
  metaCache.set(key, meta)
  return meta
}

async function loadPage(
  mode: 'all' | 'official',
  tier: PanelScope,
  axis: SkillAxisKey,
  pageNum: number,
  meta: PaginatedMeta,
): Promise<SkillLeaderboardIndexRow[]> {
  const key = pageKey(mode, tier, axis, pageNum)
  const cached = pageCache.get(key)
  if (cached) return cached

  const response = await fetch(
    `${dataBase}skill-leaderboards/${mode}/${tier}/${axis}/page-${pageNum}.json`
  )

  if (!response.ok) {
    throw new Error(`分页数据加载失败（HTTP ${response.status}）`)
  }

  const pageData = (await response.json()) as PaginatedPage
  
  // Expand rows back to objects using meta.rowFields
  const expandedRows = pageData.rows.map((row) => {
    const obj: Record<string, unknown> = {}
    meta.rowFields.forEach((field, index) => {
      obj[field] = row[index]
    })
    return obj
  }) as unknown as SkillLeaderboardIndexRow[]

  // Add to cache with LRU eviction
  pageCache.set(key, expandedRows)
  if (pageCache.size > MAX_PAGE_CACHE) {
    const oldestKey = pageCache.keys().next().value
    if (oldestKey) pageCache.delete(oldestKey)
  }

  return expandedRows
}

function filterRows(
  rows: SkillLeaderboardIndexRow[],
  query: string,
): SkillLeaderboardIndexRow[] {
  if (!query.trim()) return rows

  const needle = query.trim().toLowerCase()
  return rows.filter((row: SkillLeaderboardIndexRow) => {
    const hay = `${row.name || ''}\u0001${row.org || ''}\u0001${row.key || ''}`.toLowerCase()
    return hay.includes(needle)
  })
}

scope.onmessage = (event: MessageEvent<SkillWorkerRequest>) => {
  const message = event.data

  if (message.type === 'init') {
    dataBase = message.base.endsWith('/') ? message.base : `${message.base}/`
    return
  }

  const reply = (promise: Promise<void>) =>
    promise.catch((error: unknown) => {
      post({
        type: 'error',
        id: message.type === 'query' ? message.id : undefined,
        message: error instanceof Error ? error.message : '题型榜计算失败',
      })
    })

  void reply(
    (async () => {
      const meta = await loadMeta(message.mode, message.tier, message.axis)
      
      // Load the requested page
      const pageRows = await loadPage(
        message.mode,
        message.tier,
        message.axis,
        message.page,
        meta,
      )

      // Apply search filter if needed
      const filteredRows = filterRows(pageRows, message.query)

      post({
        type: 'result',
        id: message.id,
        rows: filteredRows,
        total: message.query.trim() ? filteredRows.length : meta.totalPlayers,
        totalPages: message.query.trim() ? 1 : meta.totalPages,
        page: message.page,
      })
    })()
  )
}

export {}
