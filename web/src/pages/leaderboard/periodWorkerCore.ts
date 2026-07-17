import type { PeriodRow } from '../../lib/data'
import { buildSchoolOptions, type SchoolOption } from './schools'
import { buildPeriodBoard, type PeriodBoardRow } from './period'

export interface PeriodPageResult {
  rows: PeriodBoardRow[]
  total: number
  overallTotal: number
  page: number
  pageCount: number
  schoolOptions: SchoolOption[]
}

export interface PeriodSnapshot {
  rows: PeriodBoardRow[]
  schoolOptions: SchoolOption[]
}

export function buildPeriodSnapshot(
  source: readonly PeriodRow[],
  toInt: number,
): PeriodSnapshot {
  const rows = buildPeriodBoard(source, 0, toInt)
  return { rows, schoolOptions: buildSchoolOptions(rows) }
}

export function paginatePeriodSnapshot(
  snapshot: PeriodSnapshot,
  org: string | null,
  requestedPage: number,
  pageSize: number,
): PeriodPageResult {
  if (pageSize <= 0) throw new Error('pageSize must be positive')
  const filtered = org
    ? snapshot.rows.filter((row) => row.org === org)
    : snapshot.rows
  const total = filtered.length
  const pageCount = Math.max(1, Math.ceil(total / pageSize))
  const page = Math.min(Math.max(1, requestedPage), pageCount)
  const start = (page - 1) * pageSize

  return {
    rows: filtered.slice(start, start + pageSize),
    total,
    overallTotal: snapshot.rows.length,
    page,
    pageCount,
    schoolOptions: snapshot.schoolOptions,
  }
}

/**
 * Build a date snapshot and return only the requested page. This function runs
 * inside a module Worker in production; keeping it pure makes the ranking,
 * school filtering, and stale-page clamping independently testable.
 */
export function buildPeriodPage(
  source: readonly PeriodRow[],
  toInt: number,
  org: string | null,
  requestedPage: number,
  pageSize: number,
): PeriodPageResult {
  return paginatePeriodSnapshot(
    buildPeriodSnapshot(source, toInt),
    org,
    requestedPage,
    pageSize,
  )
}
