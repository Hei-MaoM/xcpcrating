import { describe, expect, it } from 'vitest'
import type { PeriodRow } from '../../lib/data'
import { buildPeriodPage } from './periodWorkerCore'

describe('buildPeriodPage', () => {
  const rows: PeriodRow[] = [
    ['a', 'A', 'X', [20230101], [2100]],
    ['b', 'B', 'Y', [20230102], [2000]],
    ['c', 'C', 'X', [20230103], [1900]],
    ['d', 'D', 'Z', [20240101], [1800]],
  ]

  it('returns only the requested page plus compact aggregate metadata', () => {
    const result = buildPeriodPage(rows, 20231231, null, 1, 2)
    expect(result.rows.map((row) => row.key)).toEqual(['a', 'b'])
    expect(result.total).toBe(3)
    expect(result.overallTotal).toBe(3)
    expect(result.page).toBe(1)
    expect(result.pageCount).toBe(2)
    expect(result.schoolOptions).toEqual([
      { org: 'X', count: 2 },
      { org: 'Y', count: 1 },
    ])
  })

  it('filters by school while preserving board-global ranks', () => {
    const result = buildPeriodPage(rows, 20231231, 'X', 1, 100)
    expect(result.rows.map((row) => [row.key, row.rank])).toEqual([
      ['a', 1],
      ['c', 3],
    ])
    expect(result.total).toBe(2)
    expect(result.overallTotal).toBe(3)
  })

  it('clamps stale page numbers after filtering', () => {
    const result = buildPeriodPage(rows, 20231231, 'Y', 99, 2)
    expect(result.page).toBe(1)
    expect(result.rows.map((row) => row.key)).toEqual(['b'])
  })
})
