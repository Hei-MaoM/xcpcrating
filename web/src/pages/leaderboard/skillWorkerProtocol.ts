import type { SkillAxisKey, PanelScope } from '../../lib/data'

/**
 * Seven-dimension board worker protocol.
 *
 * The main thread cannot rely on ``document.baseURI`` inside the worker, so it
 * sends the resolved data base once during ``init``.
 */
export type SkillWorkerRequest =
  | { type: 'init'; base: string }
  | { type: 'warm'; mode: 'all' | 'official'; tier: PanelScope; axis: SkillAxisKey }
  | {
      type: 'query'
      id: number
      mode: 'all' | 'official'
      tier: PanelScope
      axis: SkillAxisKey
      query: string
      page: number
      pageSize: number
    }

export type SkillWorkerResponse =
  | { type: 'warmed'; mode: 'all' | 'official'; tier: PanelScope; axis: SkillAxisKey }
  | {
      type: 'result'
      id: number
      rows: unknown[]
      total: number
      totalPages: number
      page: number
    }
  | { type: 'error'; id?: number; message: string }
