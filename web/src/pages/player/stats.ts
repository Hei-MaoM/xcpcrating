/*
 * Player-derived statistics. Pure functions over the history array — no I/O,
 * no mutation. The exporter ships history already sorted ascending by startAt,
 * but we never rely on that for aggregate counts (only for the career span we
 * read both ends defensively).
 */

import {
  MEDAL_TIER_ORDER,
  type MedalCounts,
  type MedalTier,
  type PlayerHistoryEntry,
  type PlayerMedals,
} from '../../lib/data'

/** One tier's medals plus its tier id, ready to render as a row. */
export interface MedalTierRow {
  tier: MedalTier
  counts: MedalCounts
}

/**
 * The tiers a player actually medaled in, in display order (final → provincial).
 * Reads defensively: the `medals` field is optional and Partial (the exporter
 * omits zero-medal tiers and medal-less players entirely), and we additionally
 * skip any tier whose three colors all round to zero. Returns an empty array
 * when the player has no medals at all.
 */
export function medalTierRows(medals: PlayerMedals | undefined): MedalTierRow[] {
  if (!medals) return []
  const rows: MedalTierRow[] = []
  for (const tier of MEDAL_TIER_ORDER) {
    const counts = medals[tier]
    if (!counts) continue
    if (counts.gold > 0 || counts.silver > 0 || counts.bronze > 0) {
      rows.push({ tier, counts })
    }
  }
  return rows
}

/** Whether a player earned at least one medal in any tier. */
export function hasAnyMedal(medals: PlayerMedals | undefined): boolean {
  return medalTierRows(medals).length > 0
}

/** Career span endpoints as ISO strings, or null when history is empty. */
export interface CareerSpan {
  firstAt: string | null
  lastAt: string | null
}

/**
 * First and last contest timestamps. Computed by min/max so the result is
 * correct even if a future export ever delivered history out of order.
 */
export function careerSpan(history: readonly PlayerHistoryEntry[]): CareerSpan {
  if (history.length === 0) return { firstAt: null, lastAt: null }

  let firstAt = history[0].startAt
  let lastAt = history[0].startAt
  let firstMs = Date.parse(firstAt)
  let lastMs = firstMs

  for (const h of history) {
    const ms = Date.parse(h.startAt)
    if (Number.isNaN(ms)) continue
    if (ms < firstMs) {
      firstMs = ms
      firstAt = h.startAt
    }
    if (ms > lastMs) {
      lastMs = ms
      lastAt = h.startAt
    }
  }

  return { firstAt, lastAt }
}

/** Best (lowest) rank achieved, or null when history is empty. */
export function bestRank(history: readonly PlayerHistoryEntry[]): number | null {
  if (history.length === 0) return null
  return history.reduce((best, h) => Math.min(best, h.rank), Infinity)
}

/**
 * History sorted ascending by startAt — a defensive copy so callers never
 * mutate the source array and chart/table ordering is guaranteed.
 */
export function sortedByTime(
  history: readonly PlayerHistoryEntry[],
): PlayerHistoryEntry[] {
  return [...history].sort(
    (a, b) => Date.parse(a.startAt) - Date.parse(b.startAt),
  )
}
