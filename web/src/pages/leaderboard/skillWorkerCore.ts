import type { SkillLeaderboardIndexRow } from '../../lib/data'
import {
  buildSkillLeaderboardIndexRows,
  filterSkillLeaderboardRows,
  paginateSkillLeaderboardRows,
  type SkillLeaderboardRow,
} from './skillBoardPresentation'

/**
 * Pure part of the thirteen-dimension board, shared by the Web Worker and the
 * main-thread fallback so both compute identical ranks, filtering and paging.
 */

export interface SkillBoardPage {
  rows: SkillLeaderboardRow[]
  total: number
  totalPages: number
  page: number
}

/** Build exactly one viewport of the board; the page is clamped to the result. */
export function buildSkillBoardPage(
  rows: readonly SkillLeaderboardIndexRow[],
  query: string,
  page: number,
  pageSize: number,
): SkillBoardPage {
  const all = buildSkillLeaderboardIndexRows(rows)
  const filtered = filterSkillLeaderboardRows(all, query)
  const size = Math.max(1, Math.floor(pageSize))
  const totalPages = Math.max(1, Math.ceil(filtered.length / size))
  const safePage = Math.min(Math.max(1, Math.floor(page) || 1), totalPages)
  return {
    rows: paginateSkillLeaderboardRows(filtered, safePage, size),
    total: filtered.length,
    totalPages,
    page: safePage,
  }
}
