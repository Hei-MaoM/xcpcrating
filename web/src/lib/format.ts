/*
 * Display formatters. Pure functions, locale-stable, null-safe.
 * UI copy is Simplified Chinese; numbers stay tabular via CSS.
 */

const DATE_FMT = new Intl.DateTimeFormat('zh-CN', {
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
})

const DATETIME_FMT = new Intl.DateTimeFormat('zh-CN', {
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
})

/** Parse an ISO-ish timestamp into a Date, or null if unparseable. */
function toDate(value: string | number | null | undefined): Date | null {
  if (value === null || value === undefined || value === '') return null
  const d = new Date(value)
  return Number.isNaN(d.getTime()) ? null : d
}

/** Date only, e.g. 2026/06/12. */
export function formatDate(value: string | number | null | undefined): string {
  const d = toDate(value)
  return d ? DATE_FMT.format(d) : '—'
}

/** Date + time, e.g. 2026/06/12 14:30. */
export function formatDateTime(
  value: string | number | null | undefined,
): string {
  const d = toDate(value)
  return d ? DATETIME_FMT.format(d) : '—'
}

/** Year as a plain string, e.g. 2026. Useful for the contest year filter. */
export function formatYear(
  value: string | number | null | undefined,
): string {
  const d = toDate(value)
  return d ? String(d.getFullYear()) : '—'
}

/** Rating / performance score, one decimal place. Null renders as a dash. */
export function formatScore(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return value.toFixed(1)
}

/** A signed score delta with explicit + / − sign, one decimal. */
export function formatScoreDelta(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  const sign = value > 0 ? '+' : value < 0 ? '−' : '±'
  return `${sign}${Math.abs(value).toFixed(1)}`
}

/** Rank as 1-based ordinal, e.g. 第 3. Null renders as a dash. */
export function formatRank(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return `第 ${value}`
}

/** Bare rank number for the rank column (no prefix). */
export function formatRankNumber(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return String(value)
}

/**
 * ICPC-style penalty time. Penalty is stored in minutes; render as minutes
 * with a thin-space-grouped thousands separator for readability.
 */
export function formatPenalty(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return new Intl.NumberFormat('zh-CN').format(Math.round(value))
}

/** Solved problem count. */
export function formatSolved(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return String(value)
}

/** Percentage with no decimals, e.g. 73%. Input is a 0..1 fraction. */
export function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return `${Math.round(value * 100)}%`
}

/** Prediction deviation direction relative to actual rank. */
export type DeviationDirection = 'up' | 'down' | 'flat'

/**
 * Compare predicted rank against actual rank. A smaller actual rank than
 * predicted means the team out-performed the prediction (▲, "up").
 */
export function deviationDirection(
  predictedRank: number | null | undefined,
  actualRank: number | null | undefined,
): DeviationDirection {
  if (
    predictedRank === null ||
    predictedRank === undefined ||
    actualRank === null ||
    actualRank === undefined
  ) {
    return 'flat'
  }
  if (actualRank < predictedRank) return 'up'
  if (actualRank > predictedRank) return 'down'
  return 'flat'
}

/** Absolute rank gap between prediction and reality. */
export function rankGap(
  predictedRank: number | null | undefined,
  actualRank: number | null | undefined,
): number | null {
  if (
    predictedRank === null ||
    predictedRank === undefined ||
    actualRank === null ||
    actualRank === undefined
  ) {
    return null
  }
  return Math.abs(actualRank - predictedRank)
}
