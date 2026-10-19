/**
 * Post-contest review: Spearman rho of XCPC Rating preview ranks vs actual ranks.
 * Official teams with submissions and a known pre-contest rating only.
 * Ties use average ranks. The coefficient is not a percentage.
 */
import type { ContestTeam } from './data'

export interface ContestReviewScore {
  value: number | null
  sampleSize: number
}

function averageRanks(values: readonly number[]): number[] {
  const order = values.map((_, index) => index)
  order.sort((left, right) => {
    const delta = values[left] - values[right]
    return delta !== 0 ? delta : left - right
  })
  const ranks = Array<number>(values.length).fill(0)
  let start = 0
  while (start < order.length) {
    let end = start
    while (end + 1 < order.length && values[order[end + 1]] === values[order[start]]) {
      end += 1
    }
    const average = (start + end) / 2 + 1
    for (let index = start; index <= end; index += 1) {
      ranks[order[index]] = average
    }
    start = end + 1
  }
  return ranks
}

function pearson(xs: readonly number[], ys: readonly number[]): number | null {
  const n = xs.length
  if (n < 2) return null
  let meanX = 0
  let meanY = 0
  for (let i = 0; i < n; i += 1) {
    meanX += xs[i]
    meanY += ys[i]
  }
  meanX /= n
  meanY /= n
  let numerator = 0
  let dx = 0
  let dy = 0
  for (let i = 0; i < n; i += 1) {
    const x = xs[i] - meanX
    const y = ys[i] - meanY
    numerator += x * y
    dx += x * x
    dy += y * y
  }
  if (dx === 0 || dy === 0) return null
  return numerator / Math.sqrt(dx * dy)
}

/** Spearman rho for aligned preview/actual values. Lower values are better ranks. */
export function spearmanRho(preview: readonly number[], actual: readonly number[]): number | null {
  if (preview.length !== actual.length) return null
  return pearson(averageRanks(preview), averageRanks(actual))
}

function isReviewTeam(team: ContestTeam): boolean {
  return (
    team.official === true &&
    team.rankOfficial != null &&
    Number.isFinite(team.rankOfficial) &&
    team.preRatingOfficial != null &&
    Number.isFinite(team.preRatingOfficial) &&
    (team.knownMembersOfficial ?? 0) >= 1
  )
}

/** XCPC Rating review score for one contest. */
export function contestXCPCRatingReview(teams: readonly ContestTeam[]): ContestReviewScore {
  const sample = teams.filter(isReviewTeam)
  if (sample.length < 2) return { value: null, sampleSize: sample.length }
  const preview = sample.map((team) => -team.preRatingOfficial!)
  const actual = sample.map((team) => team.rankOfficial!)
  return { value: spearmanRho(preview, actual), sampleSize: sample.length }
}

export function formatReviewRho(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—'
  return value.toFixed(3)
}
