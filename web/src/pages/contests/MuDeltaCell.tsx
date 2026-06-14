import { formatScoreDelta } from '../../lib/format'

interface MuDeltaCellProps {
  /** Average change in team members' skill mean μ; null renders a ghost dash. */
  muDelta: number | null
}

/** Tooltip shared by the column header and every cell. */
export const MU_DELTA_TOOLTIP = '队员真实评价的平均变化（不含新手显示分解锁）'

type Direction = 'rise' | 'fall' | 'flat'

const ARROW: Record<Direction, string> = {
  rise: '▲',
  fall: '▼',
  flat: '–',
}

function directionOf(muDelta: number): Direction {
  if (muDelta > 0) return 'rise'
  if (muDelta < 0) return 'fall'
  return 'flat'
}

/**
 * Per-team μ change for a contest. ▲ marks a rise (rendered red, the "scored
 * up" convention for this board) and ▼ marks a fall (rendered green); both use
 * the colorblind-safe token pair. Null (ghost/unrated team) renders a quiet
 * em-dash with no arrow. Magnitude is the signed score delta to one decimal.
 */
export function MuDeltaCell({ muDelta }: MuDeltaCellProps) {
  if (muDelta === null || Number.isNaN(muDelta)) {
    return (
      <span className="mu-delta mu-delta--empty" title={MU_DELTA_TOOLTIP}>
        —
      </span>
    )
  }

  const dir = directionOf(muDelta)
  return (
    <span className={`mu-delta mu-delta--${dir}`} title={MU_DELTA_TOOLTIP}>
      <span aria-hidden="true">{ARROW[dir]}</span>
      <span>{formatScoreDelta(muDelta)}</span>
    </span>
  )
}
