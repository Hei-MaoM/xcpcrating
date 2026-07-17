/// <reference lib="webworker" />

import type { PeriodRow } from '../../lib/data'
import {
  buildPeriodSnapshot,
  paginatePeriodSnapshot,
  type PeriodSnapshot,
} from './periodWorkerCore'
import type {
  PeriodBounds,
  PeriodWorkerRequest,
  PeriodWorkerResponse,
} from './periodWorkerProtocol'

const scope = self as DedicatedWorkerGlobalScope
let source: PeriodRow[] | null = null
let cachedTo: number | null = null
let cachedSnapshot: PeriodSnapshot | null = null

function post(message: PeriodWorkerResponse): void {
  scope.postMessage(message)
}

function dataBounds(rows: readonly PeriodRow[]): PeriodBounds | null {
  let lo = Infinity
  let hi = -Infinity
  for (const [, , , dates] of rows) {
    if (dates.length === 0) continue
    lo = Math.min(lo, dates[0])
    hi = Math.max(hi, dates[dates.length - 1])
  }
  return Number.isFinite(lo) ? { lo, hi } : null
}

async function load(url: string): Promise<void> {
  const response = await fetch(url)
  if (!response.ok) throw new Error(`时间段数据加载失败（HTTP ${response.status}）`)
  source = (await response.json()) as PeriodRow[]
  const bounds = dataBounds(source)
  if (!bounds) throw new Error('时间段数据为空')
  cachedTo = null
  cachedSnapshot = null
  post({ type: 'loaded', bounds })
}

scope.onmessage = (event: MessageEvent<PeriodWorkerRequest>) => {
  const message = event.data
  if (message.type === 'load') {
    void load(message.url).catch((error: unknown) => {
      post({
        type: 'error',
        message: error instanceof Error ? error.message : '时间段数据加载失败',
      })
    })
    return
  }

  if (!source) {
    post({ type: 'error', id: message.id, message: '时间段数据尚未加载完成' })
    return
  }
  try {
    if (cachedTo !== message.toInt || !cachedSnapshot) {
      cachedSnapshot = buildPeriodSnapshot(source, message.toInt)
      cachedTo = message.toInt
    }
    post({
      type: 'result',
      id: message.id,
      ...paginatePeriodSnapshot(
        cachedSnapshot,
        message.org,
        message.page,
        message.pageSize,
      ),
    })
  } catch (error: unknown) {
    post({
      type: 'error',
      id: message.id,
      message: error instanceof Error ? error.message : '时间段榜单计算失败',
    })
  }
}

export {}
