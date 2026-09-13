/// <reference lib="webworker" />

import type { SkillAxisKey, PanelScope, SkillLeaderboardIndex } from '../../lib/data'
import { decodeSkillLeaderboardRows } from '../../lib/skillLeaderboardCodec'
import { buildSkillBoardPage } from './skillWorkerCore'
import type { SkillWorkerRequest, SkillWorkerResponse } from './skillWorkerProtocol'

/**
 * Seven-dimension board worker.
 *
 * One axis board is a 6 MB JSON document; fetching, decoding and ranking it on
 * the main thread blocked the first paint of the board. The worker keeps the
 * decoded board for the most recent calibers and answers with one page of rows,
 * so the main thread only ever sees the thirty rows it renders.
 */

const scope = self as DedicatedWorkerGlobalScope
const MAX_CACHED_BOARDS = 2
const boards = new Map<string, SkillLeaderboardIndex>()
let dataBase = 'data/'

function post(message: SkillWorkerResponse): void {
  scope.postMessage(message)
}

function boardKey(mode: string, tier: string, axis: string): string {
  return `${mode}/${tier}/${axis}`
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
    // Older bundles only carry the overall caliber.
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

  if (message.type === 'warm') {
    void reply(
      loadBoard(message.mode, message.tier, message.axis).then(() => {
        post({ type: 'warmed', mode: message.mode, tier: message.tier, axis: message.axis })
      }),
    )
    return
  }

  void reply(
    loadBoard(message.mode, message.tier, message.axis).then((board) => {
      const page = buildSkillBoardPage(board.rows, message.query, message.page, message.pageSize)
      post({ type: 'result', id: message.id, ...page })
    }),
  )
}

export {}
