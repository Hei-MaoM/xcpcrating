import type { BadgeVariant } from '../../components/ui'

/**
 * Contest series taxonomy. The exporter emits three category ids; everything
 * else (labels, badge styling, filter order) is derived here so the pages stay
 * free of scattered string literals.
 */
export type CategoryId = 'icpc' | 'ccpc' | 'provincial'

/** Filter values include an "all" pseudo-category. */
export type SeriesFilter = 'all' | CategoryId

export const SERIES_FILTERS: readonly SeriesFilter[] = [
  'all',
  'icpc',
  'ccpc',
  'provincial',
] as const

const FILTER_LABELS: Record<SeriesFilter, string> = {
  all: '全部',
  icpc: 'ICPC',
  ccpc: 'CCPC',
  provincial: '省赛',
}

/** Human label for a series filter chip. */
export function seriesLabel(filter: SeriesFilter): string {
  return FILTER_LABELS[filter] ?? filter
}

/** Human label for a contest's own category badge. */
export function categoryLabel(category: string): string {
  if (category === 'icpc') return 'ICPC'
  if (category === 'ccpc') return 'CCPC'
  if (category === 'provincial') return '省赛'
  return category
}

/**
 * Badge tone per category. Kept neutral/accent only — medal colors are
 * reserved for podium semantics, never for taxonomy.
 */
export function categoryBadgeVariant(category: string): BadgeVariant {
  return category === 'provincial' ? 'neutral' : 'accent'
}

/** Type guard narrowing an arbitrary string to a known filter value. */
export function isSeriesFilter(value: string | null): value is SeriesFilter {
  return value !== null && (SERIES_FILTERS as readonly string[]).includes(value)
}
