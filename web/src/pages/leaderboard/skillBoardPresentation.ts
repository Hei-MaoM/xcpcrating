import type {
  PanelScope,
  PanelGrade,
  PlayerSkillAxis,
  PlayerSkillPanel,
  SkillAxisKey,
  SkillLeaderboardIndexRow,
} from '../../lib/data'
import { skillAxisRating, skillAxisStatus, type SkillAxisState } from '../player/skillPanelPresentation'

export type SkillLeaderboardMode = 'all' | 'official'

export interface SkillLeaderboardPlayer {
  key: string
  name: string
  org: string
  skillPanel?: PlayerSkillPanel
}

export interface SkillLeaderboardRow {
  key: string
  name: string
  org: string
  rank: number | null
  score: number | null
  mastery: number | null
  topPercent: number | null
  grade: PanelGrade | null
  uniqueProblems: number
  coverage: number
  rankScore: number | null
  effectiveProblems: number
  evidenceLevel: string
  confidence: number
  status: SkillAxisState
}

/** Keep tiny percentiles readable instead of rounding them down to 0.0%. */
export function formatSkillTopPercent(
  value: number | null | undefined,
  rank?: number | null,
): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—'
  if (value <= 1 && typeof rank === 'number' && Number.isFinite(rank) && rank >= 1) {
    return `第 ${Math.round(rank)} 名`
  }
  return `前 ${value < 1 ? value.toFixed(2) : value.toFixed(1)}%`
}

/** Convert a precomputed axis index into display rows without loading player shards. */
export function buildSkillLeaderboardIndexRows(
  rows: readonly SkillLeaderboardIndexRow[],
): SkillLeaderboardRow[] {
  let previousScore: number | null = null
  let previousRank = 0
  return rows.map((row, index) => {
    const orderingScore = row.rankScore ?? row.score
    if (previousScore === null || orderingScore !== previousScore) {
      previousRank = index + 1
      previousScore = orderingScore
    }
    const status = 'ready' as SkillAxisState
    return {
      key: row.key,
      name: row.name,
      org: row.org,
      rank: status === 'ready' ? previousRank : null,
      score: row.score,
      mastery: null,
      topPercent: status === 'ready' ? row.topPercent : null,
      grade: status === 'ready' ? row.grade : null,
      uniqueProblems: row.uniqueProblems,
      coverage: row.coverage,
      rankScore: row.rankScore ?? row.score,
      effectiveProblems: row.effectiveProblems ?? row.uniqueProblems,
      evidenceLevel: row.evidenceLevel ?? 'legacy',
      confidence: row.confidence ?? 1,
      status,
    }
  })
}

/** Return one viewport-sized slice without changing the precomputed global ranks. */
export function paginateSkillLeaderboardRows<T>(
  rows: readonly T[],
  page: number,
  pageSize: number,
): T[] {
  if (!Number.isFinite(page) || !Number.isFinite(pageSize) || pageSize <= 0) return []
  const safePage = Math.max(1, Math.floor(page))
  const safePageSize = Math.max(1, Math.floor(pageSize))
  const start = (safePage - 1) * safePageSize
  return Array.from(rows.slice(start, start + safePageSize))
}

/** Filter by the visible player name, organisation, or canonical key. */
export function filterSkillLeaderboardRows(
  rows: readonly SkillLeaderboardRow[],
  query: string,
): SkillLeaderboardRow[] {
  const needle = query.trim().toLocaleLowerCase()
  return rows.filter((row) => {
    const matchesQuery = !needle || `${row.name} ${row.org} ${row.key}`.toLocaleLowerCase().includes(needle)
    return matchesQuery
  })
}

function metricFor(
  player: SkillLeaderboardPlayer,
  mode: SkillLeaderboardMode,
  tier: PanelScope,
  axis: SkillAxisKey,
): PlayerSkillAxis | undefined {
  return player.skillPanel?.[mode]?.[tier]?.axes[axis]
}

function scoreOf(metric: PlayerSkillAxis | undefined): number | null {
  return skillAxisRating(metric)
}

/** Build one axis leaderboard; rows without a computed metric remain visible at the bottom. */
export function buildSkillLeaderboardRows(
  players: readonly SkillLeaderboardPlayer[],
  mode: SkillLeaderboardMode,
  tier: PanelScope,
  axis: SkillAxisKey,
): SkillLeaderboardRow[] {
  const rows: SkillLeaderboardRow[] = players
    .filter((player) => Boolean(player.skillPanel?.[mode]?.[tier]))
    .map((player) => {
      const metric = metricFor(player, mode, tier, axis)
      const status = skillAxisStatus(metric)
      return {
        key: player.key,
        name: player.name,
        org: player.org,
        rank: null,
        score: scoreOf(metric),
        mastery: metric?.mastery ?? null,
        topPercent: status === 'ready' ? metric?.topPercent ?? null : null,
        grade: status === 'ready' ? metric?.grade ?? null : null,
        uniqueProblems: metric?.uniqueProblems ?? 0,
        coverage: metric?.coverage ?? 0,
        rankScore: metric?.rankScore ?? scoreOf(metric),
        effectiveProblems: metric?.effectiveProblems ?? metric?.uniqueProblems ?? 0,
        evidenceLevel: metric?.evidenceLevel ?? 'legacy',
        confidence: metric?.confidence ?? 1,
        status,
      }
    })

  rows.sort((left, right) => {
    const leftReady = left.status === 'ready'
    const rightReady = right.status === 'ready'
    if (leftReady !== rightReady) return leftReady ? -1 : 1
    if (left.score !== null && right.score !== null && left.score !== right.score) {
      return right.score - left.score
    }
    if (left.score !== null && right.score === null) return -1
    if (left.score === null && right.score !== null) return 1
    return left.key.localeCompare(right.key)
  })

  let previousScore: number | null = null
  let previousRank = 0
  let eligiblePosition = 0
  for (const row of rows) {
    if (row.status !== 'ready' || row.score === null) continue
    eligiblePosition += 1
    if (previousScore === null || row.score !== previousScore) {
      previousRank = eligiblePosition
      previousScore = row.score
    }
    row.rank = previousRank
  }
  return rows
}

export type SkillLeaderboardEmptyState = 'loading' | 'unavailable' | 'empty'

export function skillLeaderboardEmptyMessage(
  state: SkillLeaderboardEmptyState,
): string {
  if (state === 'loading') return '正在加载题型维度排行榜…'
  if (state === 'unavailable') {
    return '当前数据包没有题型排行榜索引，请重新导出包含 skillPanel 的数据。'
  }
  return '当前题型暂无匹配的选手。'
}
