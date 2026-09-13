export interface RadarPoint {
  x: number
  y: number
}

function clampPercent(value: number): number {
  return Math.min(100, Math.max(0, value))
}

/** Convert a top-percentile rank into an outward-is-better radar strength. */
export function metricStrength(topPercent: number | null): number | null {
  if (topPercent === null || !Number.isFinite(topPercent)) return null
  return 100 - clampPercent(topPercent)
}

/** Lay values out clockwise on a regular polygon, starting at twelve o'clock. */
export function radarPoints(
  values: readonly (number | null)[],
  radius: number,
  centerX: number,
  centerY: number,
): RadarPoint[] {
  if (values.length === 0) return []

  return values.map((value, index) => {
    const strength =
      value === null || !Number.isFinite(value) ? 0 : clampPercent(value)
    const angle = -Math.PI / 2 + (index * 2 * Math.PI) / values.length
    const pointRadius = (radius * strength) / 100

    return {
      x: centerX + Math.cos(angle) * pointRadius,
      y: centerY + Math.sin(angle) * pointRadius,
    }
  })
}

export function radarPointString(points: readonly RadarPoint[]): string {
  return points.map(({ x, y }) => `${x.toFixed(2)},${y.toFixed(2)}`).join(' ')
}
