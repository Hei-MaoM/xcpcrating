import type { ContestIndexEntry, MedalTier } from '../../lib/data'
import {
  ALL_COMPETITION_SEASONS,
  competitionSeasonKey,
} from '../contests/competition-season'
export { contestCategoryBadgeLabel } from '../contests/categories'

export type ContestRankingTier = MedalTier | 'online'
export type ContestTierFilter = 'all' | ContestRankingTier

/** Canonical query/display order for independently selectable tiers. */
export const CONTEST_TIER_FILTERS: readonly ContestRankingTier[] = [
  'final',
  'regional',
  'invitational',
  'provincial',
  'online',
]

const CONTEST_TIER_LABELS: Record<ContestTierFilter, string> = {
  all: '全部',
  final: 'Final',
  regional: '区域赛',
  invitational: '邀请赛',
  provincial: '省赛',
  online: '网络赛',
}

export function contestTierLabel(tier: ContestTierFilter): string {
  return CONTEST_TIER_LABELS[tier]
}

function normalizeContestTierSelection(
  tiers: ReadonlyArray<ContestRankingTier>,
): ContestRankingTier[] {
  const requested = new Set<string>(tiers)
  const canonical = CONTEST_TIER_FILTERS.filter((tier) =>
    requested.has(tier),
  )
  // Selecting every category is semantically identical to selecting none: all.
  return canonical.length === CONTEST_TIER_FILTERS.length ? [] : canonical
}

/**
 * Parse the comma-separated `tier` query. Unknown/empty tokens are ignored;
 * an empty result and all five valid categories both canonicalize to "all".
 */
export function parseContestTierSelection(
  raw: string | null,
): ContestRankingTier[] {
  if (!raw) return []
  const tokens = new Set(raw.split(',').map((token) => token.trim()))
  return normalizeContestTierSelection(
    CONTEST_TIER_FILTERS.filter((tier) => tokens.has(tier)),
  )
}

/** Return the canonical query value, or null when the selection means all. */
export function serializeContestTierSelection(
  tiers: ReadonlyArray<ContestRankingTier>,
): string | null {
  const canonical = normalizeContestTierSelection(tiers)
  return canonical.length > 0 ? canonical.join(',') : null
}

/** Toggle one tier; from "all", the first click selects only that tier. */
export function toggleContestTier(
  tiers: ReadonlyArray<ContestRankingTier>,
  tier: ContestRankingTier,
): ContestRankingTier[] {
  const canonical = normalizeContestTierSelection(tiers)
  if (canonical.length === 0) return [tier]

  const next = new Set(canonical)
  if (next.has(tier)) next.delete(tier)
  else next.add(tier)
  return normalizeContestTierSelection([...next])
}

export const CONTEST_RANKING_METRICS = [
  'bronze',
  'silver',
  'gold',
  'top3',
  'top10',
  'overall',
  'weirdness',
] as const

export type ContestRankingMetric = (typeof CONTEST_RANKING_METRICS)[number]

export interface ContestRankingRow {
  contest: ContestIndexEntry
  score: number
  /** 1-based competition rank: 1, 2, 2, 4. */
  rank: number
}

export function isContestRankingMetric(
  value: string | null,
): value is ContestRankingMetric {
  return (
    value !== null &&
    (CONTEST_RANKING_METRICS as readonly string[]).includes(value)
  )
}

function scoreFor(
  contest: ContestIndexEntry,
  metric: ContestRankingMetric,
): number | null {
  const contestMetrics = contest.contestMetrics
  if (!contestMetrics) return null
  if (
    contestMetrics.awardsMedals === false &&
    (metric === 'bronze' || metric === 'silver' || metric === 'gold')
  ) {
    return null
  }

  const value =
    metric === 'weirdness'
      ? contestMetrics.weirdness
      : contestMetrics.strength?.[metric]
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

/**
 * Build one metric board from the compact contest index.
 *
 * Filtering happens before ranking so a tier-specific view always starts
 * at rank 1. Exact exported scores tie; date/title/slug only make tied rows'
 * display order deterministic and do not split their competition rank.
 */
export function buildContestRanking(
  contests: ReadonlyArray<ContestIndexEntry>,
  metric: ContestRankingMetric,
  tiers: ReadonlyArray<ContestRankingTier>,
  season: string,
): ContestRankingRow[] {
  const canonicalTiers = normalizeContestTierSelection(tiers)
  const selectedTiers = new Set(canonicalTiers)
  const ranked = contests
    .filter(
      (contest) => {
        const tier: ContestRankingTier = contest.onlinePreliminary
          ? 'online'
          : contest.tier
        const matchesTier =
          selectedTiers.size === 0 || selectedTiers.has(tier)
        const matchesSeason =
          season === ALL_COMPETITION_SEASONS ||
          competitionSeasonKey(contest.startAt) === season
        return matchesTier && matchesSeason
      },
    )
    .map((contest) => ({ contest, score: scoreFor(contest, metric) }))
    .filter(
      (row): row is { contest: ContestIndexEntry; score: number } =>
        row.score !== null,
    )
    .sort((a, b) => {
      if (a.score !== b.score) return b.score - a.score

      const dateDifference =
        new Date(b.contest.startAt).getTime() -
        new Date(a.contest.startAt).getTime()
      if (dateDifference !== 0) return dateDifference

      const titleDifference = a.contest.title.localeCompare(
        b.contest.title,
        'zh-CN',
      )
      return titleDifference || a.contest.slug.localeCompare(b.contest.slug)
    })

  let previousScore: number | null = null
  let previousRank = 0
  return ranked.map((row, index) => {
    const rank =
      previousScore !== null && row.score === previousScore
        ? previousRank
        : index + 1
    previousScore = row.score
    previousRank = rank
    return { ...row, rank }
  })
}
