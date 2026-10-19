/// <reference lib="webworker" />

import type { SkillAxisKey, PanelScope, SkillLeaderboardIndex, SkillLeaderboardIndexRow } from '../../lib/data'
import { decodeSkillLeaderboardRows } from '../../lib/skillLeaderboardCodec'
import { buildSkillBoardPage } from './skillWorkerCore'
import type { SkillWorkerRequest, SkillWorkerResponse } from './skillWorkerProtocol'

/**
 * Skill leaderboard worker with Phase 2 paginated data support.
 *
 * Automatically detects and uses paginated data (meta.json + page-N.json) when available,
 * with graceful fallback to monolithic axis files for backward compatibility.
 */

const scope = self as DedicatedWorkerGlobalScope
const MAX_CACHED_BOARDS = 2
const boards = new Map<string, SkillLeaderboardIndex>()
let dataBase = 'data/'

// Phase 2: Pagination metadata cache
interface PaginatedMeta {
  version: string
  totalPlayers: number
  totalPages: number
  pageSize: number
  rowFields: string[]
}

const metaCache = new Map<string, PaginatedMeta | null>()  // null = not available
const pageCache = new Map<string, SkillLeaderboardIndexRow[]>()
const MAX_PAGE_CACHE = 10

function post(message: SkillWorkerResponse): void {
  scope.postMessage(message)
}

function boardKey(mode: string, tier: string, axis: string): string {
  return `${mode}/${tier}/${axis}`
}

function pageKey(mode: string, tier: string, axis: string, page: number): string {
  return `${mode}/${tier}/${axis}/p${page}`
}

async function tryLoadMeta(
  mode: 'all' | 'official',
  tier: PanelScope,
  axis: SkillAxisKey,
): Promise<PaginatedMeta | null> {
  const key = boardKey(mode, tier, axis)
  if (metaCache.has(key)) return metaCache.get(key) || null

  try {
    const response = await fetch(
      `${dataBase}skill-leaderboards/${mode}/${tier}/${axis}/meta.json`
    )
    if (!response.ok) {
      metaCache.set(key, null)
      return null
    }
    const meta = (await response.json()) as PaginatedMeta
    metaCache.set(key, meta)
    return meta
  } catch {
    metaCache.set(key, null)
    return null
  }
}

async function loadPaginatedPage(
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
  if (!response.ok) throw new Error(`分页数据加载失败（HTTP ${response.status}）`)

  const pageData = (await response.json()) as { page: number; rows: unknown[][] }
  
  // Expand array rows to objects
  const expandedRows: SkillLeaderboardIndexRow[] = pageData.rows.map((row): any => {
    const obj: any = {}
    meta.rowFields.forEach((field, index) => {
      obj[field] = row[index]
    })
    return obj as SkillLeaderboardIndexRow
  })

  // LRU cache
  pageCache.set(key, expandedRows)
  if (pageCache.size > MAX_PAGE_CACHE) {
    const oldestKey = pageCache.keys().next().value
    if (oldestKey) pageCache.delete(oldestKey)
  }

  return expandedRows
}

async function loadBoard(
  mode: 'all' | 'official',
  tier: PanelScope,
  axis: SkillAxisKey,
): Promise<SkillLeaderboardIndex> {
  const key = boardKey(mode, tier, axis)
  const cached = boards.get(key)
  if (cached) return cached

  let response = await fetch(`${dataBase}skill-leaderboards/${mode}/${tier}/${axis}.json`)
  if (!response.ok && tier === 'overall') {
    response = await fetch(`${dataBase}skill-leaderboards/${mode}/regional/${axis}.json`)
  }
  if (!response.ok) throw new Error(`题型榜数据加载失败（HTTP ${response.status}）`)

  const board = decodeSkillLeaderboardRows(
    (await response.json()) as SkillLeaderboardIndex & { rowFields?: unknown },
  )
  boards.set(key, board)
  while (boards.size > MAX_CACHED_BOARDS) {
    const oldest = boards.keys().next().value
    if (oldest === undefined) break
    boards.delete(oldest)
  }
  return board
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
      // Phase 2: Try paginated data first
      const meta = await tryLoadMeta(message.mode, message.tier, message.axis)

      if (meta) {
        // Use paginated data
        const pageRows = await loadPaginatedPage(
          message.mode,
          message.tier,
          message.axis,
          message.page,
          meta,
        )
        const page = buildSkillBoardPage(pageRows, message.query, 1, message.pageSize)
        post({
          type: 'result',
          id: message.id,
          rows: page.rows,
          total: message.query.trim() ? page.total : meta.totalPlayers,
          totalPages: message.query.trim() ? page.totalPages : meta.totalPages,
          page: message.query.trim() ? 1 : message.page,
        })
      } else {
        // Fallback to monolithic file
        const board = await loadBoard(message.mode, message.tier, message.axis)
        const page = buildSkillBoardPage(board.rows, message.query, message.page, message.pageSize)
        post({ type: 'result', id: message.id, ...page })
      }
    })()
  )
}

export {}
