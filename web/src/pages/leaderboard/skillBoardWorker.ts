import {
  dataUrl,
  getSkillLeaderboardIndex,
  type PanelScope,
  type SkillAxisKey,
} from '../../lib/data'
import { buildSkillBoardPage, type SkillBoardPage } from './skillWorkerCore'
import type { SkillWorkerRequest, SkillWorkerResponse } from './skillWorkerProtocol'

/**
 * Seven-dimension board access.
 *
 * The board's axis files are ~6 MB JSON documents; decoding and ranking them on
 * the main thread blocked the first paint. All of that runs in a module-scoped
 * worker, which caches the last two calibers and answers with a single page of
 * rows. Environments without Worker support (or a worker that fails to boot)
 * transparently fall back to the main thread with identical results.
 */

export interface SkillBoardQuery {
  mode: 'all' | 'official'
  tier: PanelScope
  axis: SkillAxisKey
  query: string
  page: number
  pageSize: number
}

interface PendingEntry {
  request: SkillBoardQuery
  resolve: (page: SkillBoardPage) => void
  reject: (error: Error) => void
}

let worker: Worker | null = null
let workerUnavailable = false
let nextRequestId = 1
const pending = new Map<number, PendingEntry>()

function createWorker(): Worker | null {
  if (worker) return worker
  if (workerUnavailable || typeof Worker === 'undefined') return null
  try {
    const instance = new Worker(new URL('./skill.worker.ts', import.meta.url), {
      type: 'module',
      name: 'skill-board',
    })
    instance.onmessage = (event: MessageEvent<SkillWorkerResponse>) => {
      handleMessage(event.data)
    }
    instance.onerror = () => {
      // A worker that failed to boot (CSP, bundler mismatch, ...) must not take
      // the board down: retire it and finish the queued work on the main thread.
      workerUnavailable = true
      instance.terminate()
      if (worker === instance) worker = null
      for (const [id, entry] of pending) {
        pending.delete(id)
        void queryOnMainThread(entry.request).then(entry.resolve, entry.reject)
      }
    }
    // The worker has no document.baseURI, so hand it the resolved data root.
    const init: SkillWorkerRequest = { type: 'init', base: dataUrl('') }
    instance.postMessage(init)
    worker = instance
    return instance
  } catch {
    workerUnavailable = true
    return null
  }
}

function handleMessage(message: SkillWorkerResponse): void {
  if (message.type === 'warmed') return
  if (message.type === 'error') {
    if (message.id === undefined) return
    const entry = pending.get(message.id)
    if (!entry) return
    pending.delete(message.id)
    // A worker-side fetch failure must not blank the board: retry the same
    // query on the main thread (which has its own request cache) and only
    // surface the error if that fails too.
    void queryOnMainThread(entry.request).then(entry.resolve, entry.reject)
    return
  }
  const entry = pending.get(message.id)
  if (!entry) return
  pending.delete(message.id)
  entry.resolve({
    rows: message.rows as SkillBoardPage['rows'],
    total: message.total,
    totalPages: message.totalPages,
    page: message.page,
  })
}

async function queryOnMainThread(request: SkillBoardQuery): Promise<SkillBoardPage> {
  const board = await getSkillLeaderboardIndex(request.mode, request.tier, request.axis)
  return buildSkillBoardPage(board.rows, request.query, request.page, request.pageSize)
}

/** Fetch, decode and cache one caliber ahead of the first board render. */
export function warmSkillBoard(
  mode: 'all' | 'official',
  tier: PanelScope,
  axis: SkillAxisKey,
): void {
  const instance = createWorker()
  if (!instance) return
  const request: SkillWorkerRequest = { type: 'warm', mode, tier, axis }
  instance.postMessage(request)
}

/** Resolve one page of the seven-dimension board. */
export function querySkillBoard(request: SkillBoardQuery): Promise<SkillBoardPage> {
  const instance = createWorker()
  if (!instance) return queryOnMainThread(request)
  return new Promise<SkillBoardPage>((resolve, reject) => {
    const id = nextRequestId
    nextRequestId += 1
    pending.set(id, { request, resolve, reject })
    instance.postMessage({ type: 'query', id, ...request })
  })
}
