/*
 * Pure logic for the 时间段 (period) board: given the official-participation
 * timelines (`period-index.json`) and a [from, to] date window, derive the board
 * of players who officially competed inside the window, each scored by their
 * official rating as of the end of the window (历史快照). Side-effect free and
 * DOM-free so it can be unit-tested and run cheaply on every (debounced) edit.
 */

import type { PeriodRow } from '../../lib/data'
import { tiedRanks } from '../../lib/rank'

/** One row of the period board, ready to render. */
export interface PeriodBoardRow {
  key: string
  name: string
  org: string
  /**
   * Official-board rating as of the last official contest <= `to`, rounded to a
   * whole number (四舍五入) — the displayed score, and the value ties are judged on.
   */
  rating: number
  /** Number of official participations inside [from, to]. */
  count: number
  /**
   * 1-based rank within the period board. Players sharing the same rounded score
   * share a rank (standard competition "1224" ranking — two tied at 1, next at 3).
   */
  rank: number
}

/**
 * Convert an `<input type="date">` value (`YYYY-MM-DD`) to the `YYYYMMDD` int the
 * timelines use, or null when empty / malformed. Strict on shape so a partial
 * edit never yields a misleading window.
 */
export function dateToInt(value: string | null | undefined): number | null {
  if (!value) return null
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value)
  if (!match) return null
  return Number(`${match[1]}${match[2]}${match[3]}`)
}

/** A scored row before ranking: keeps the full-precision snapshot for ordering. */
interface ScoredRow {
  key: string
  name: string
  org: string
  /** Full-precision snapshot rating (ordering key; displayed value is rounded). */
  exact: number
  count: number
}

/**
 * Build the period board. A player qualifies when they have at least one
 * official participation in `[fromInt, toInt]`; their score is the rating after
 * the last official contest on-or-before `toInt` (so the board reads as a
 * snapshot at the window's end), rounded to a whole number for display. `org`,
 * when set, restricts to that school.
 *
 * Rows are ordered by full-precision snapshot descending, but ranked on the
 * rounded score: players whose scores round to the same whole number share a
 * rank (1224 ties). Each row's `dates` are assumed ascending (the exporter writes
 * them chronologically), which lets the per-row scan stop early. Returns an empty
 * board for an inverted window (`fromInt > toInt`).
 */
export function buildPeriodBoard(
  rows: ReadonlyArray<PeriodRow>,
  fromInt: number,
  toInt: number,
  org?: string | null,
): PeriodBoardRow[] {
  if (fromInt > toInt) return []

  const scored: ScoredRow[] = []
  for (const [key, name, rowOrg, dates, ratings] of rows) {
    if (org && rowOrg !== org) continue

    let count = 0
    let lastIdx = -1
    for (let i = 0; i < dates.length; i += 1) {
      const day = dates[i]
      if (day > toInt) break // ascending: nothing further is on-or-before `to`
      lastIdx = i
      if (day >= fromInt) count += 1
    }
    // No official contest inside the window → not on this board. (count > 0
    // guarantees lastIdx points at a contest <= toInt, so the snapshot exists.)
    if (count === 0) continue

    scored.push({ key, name, org: rowOrg, exact: ratings[lastIdx], count })
  }

  // Order by full-precision score (so a tie group is ordered intuitively), then
  // rank on the rounded score (shared 1224 tie helper).
  scored.sort((a, b) => b.exact - a.exact || a.key.localeCompare(b.key))
  const ranks = tiedRanks(scored.map((row) => row.exact))
  return scored.map((row, i) => ({
    key: row.key,
    name: row.name,
    org: row.org,
    rating: Math.round(row.exact),
    count: row.count,
    rank: ranks[i],
  }))
}
