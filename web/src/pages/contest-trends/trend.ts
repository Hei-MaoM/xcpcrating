import type {
  ContestIndexEntry,
  ContestStrengthScores,
} from '../../lib/data'
import {
  competitionSeasonKey,
  competitionSeasonLabel,
} from '../contests/competition-season'

/**
 * This page deliberately has a narrow scope. Finals, online preliminaries,
 * provincial contests, and restricted CCPC tracks are not folded into an
 * "other" bucket.
 */
export const CONTEST_TREND_KINDS = [
  'icpc-regional',
  'icpc-invitational',
  'ccpc-regional',
  'ccpc-invitational',
] as const

export type ContestTrendKind = (typeof CONTEST_TREND_KINDS)[number]

export const CONTEST_TREND_KIND_LABELS: Record<ContestTrendKind, string> = {
  'icpc-regional': 'ICPC 区域赛',
  'icpc-invitational': 'ICPC 邀请赛',
  'ccpc-regional': 'CCPC 区域赛',
  'ccpc-invitational': 'CCPC 邀请赛',
}

export const STRENGTH_COLUMNS: ReadonlyArray<{
  key: keyof ContestStrengthScores
  label: string
}> = [
  { key: 'bronze', label: '铜牌难度' },
  { key: 'silver', label: '银牌难度' },
  { key: 'gold', label: '金牌难度' },
  { key: 'top3', label: '前三难度' },
  { key: 'top10', label: '前十难度' },
  { key: 'overall', label: '整体难度' },
]

export interface ContestTrendRow {
  contest: ContestIndexEntry
  kind: ContestTrendKind
}

export interface ContestTrendSeason {
  season: string
  rows: ContestTrendRow[]
}

const KIND_INDEX = new Map<ContestTrendKind, number>(
  CONTEST_TREND_KINDS.map((kind, index) => [kind, index]),
)

function finiteNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

/** Return one of the four explicit trend kinds, or null when out of scope. */
export function contestTrendKind(
  contest: Pick<
    ContestIndexEntry,
    'category' | 'tier' | 'onlinePreliminary'
  >,
): ContestTrendKind | null {
  if (contest.onlinePreliminary) return null
  if (contest.category !== 'icpc' && contest.category !== 'ccpc') return null
  if (contest.tier !== 'regional' && contest.tier !== 'invitational') {
    return null
  }
  return `${contest.category}-${contest.tier}` as ContestTrendKind
}

/**
 * Map a source date to its September–August season without timezone
 * conversion. For example, 2025-09-01 through 2026-08-31 is 2025–2026.
 */
export function contestTrendSeason(startAt: string): string {
  const key = competitionSeasonKey(startAt)
  return key === null ? '未知赛季' : competitionSeasonLabel(key)
}

/**
 * Build newest-first season dossiers. Every scoped contest produces exactly
 * one row; this helper never averages, bins, smooths, or otherwise aggregates
 * difficulty values.
 */
export function buildContestTrendSeasons(
  contests: ReadonlyArray<ContestIndexEntry>,
): ContestTrendSeason[] {
  const grouped = new Map<string, ContestTrendRow[]>()

  for (const contest of contests) {
    const kind = contestTrendKind(contest)
    if (kind === null) continue
    const season = contestTrendSeason(contest.startAt)
    const rows = grouped.get(season)
    const row = { contest, kind }
    if (rows) rows.push(row)
    else grouped.set(season, [row])
  }

  const seasons = [...grouped.entries()].map(([season, rows]) => {
    rows.sort((left, right) => {
      const kindDifference =
        (KIND_INDEX.get(left.kind) ?? Number.MAX_SAFE_INTEGER) -
        (KIND_INDEX.get(right.kind) ?? Number.MAX_SAFE_INTEGER)
      if (kindDifference !== 0) return kindDifference

      const dateDifference =
        Date.parse(right.contest.startAt) - Date.parse(left.contest.startAt)
      if (Number.isFinite(dateDifference) && dateDifference !== 0) {
        return dateDifference
      }
      return (
        left.contest.title.localeCompare(right.contest.title, 'zh-CN') ||
        left.contest.slug.localeCompare(right.contest.slug)
      )
    })
    return { season, rows }
  })

  return seasons.sort((left, right) => {
    if (left.season === '未知赛季') return 1
    if (right.season === '未知赛季') return -1
    return Number(right.season.slice(0, 4)) - Number(left.season.slice(0, 4))
  })
}

/** Read one exported per-contest strength value without deriving a replacement. */
export function contestStrength(
  contest: ContestIndexEntry,
  key: keyof ContestStrengthScores,
): number | null {
  return finiteNumber(contest.contestMetrics?.strength?.[key])
}
