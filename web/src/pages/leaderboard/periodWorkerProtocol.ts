import type { PeriodPageResult } from './periodWorkerCore'

export interface PeriodBounds {
  lo: number
  hi: number
}

export type PeriodWorkerRequest =
  | { type: 'load'; url: string }
  | {
      type: 'query'
      id: number
      toInt: number
      org: string | null
      page: number
      pageSize: number
    }

export type PeriodWorkerResponse =
  | { type: 'loaded'; bounds: PeriodBounds }
  | ({ type: 'result'; id: number } & PeriodPageResult)
  | { type: 'error'; id?: number; message: string }
