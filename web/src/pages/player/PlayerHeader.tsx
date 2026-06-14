import type { PlayerDetail } from '../../lib/data'
import { formatScore, formatDate } from '../../lib/format'
import { careerSpan, bestRank } from './stats'
import { PlayerMedalsBlock } from './PlayerMedals'

interface PlayerHeaderProps {
  player: PlayerDetail
}

/** A single labelled metric in the header summary strip. */
function Metric({
  label,
  value,
  sub,
}: {
  label: string
  value: React.ReactNode
  sub?: React.ReactNode
}) {
  return (
    <div className="player-metric">
      <span className="player-metric__label">{label}</span>
      <span className="player-metric__value tnum">{value}</span>
      {sub ? <span className="player-metric__sub tnum">{sub}</span> : null}
    </div>
  )
}

/**
 * Player header: serif name display, school, the ladder score card, contest
 * count, career span, and a tiered medal block (gold/silver/bronze bucketed by
 * contest prestige).
 */
export function PlayerHeader({ player }: PlayerHeaderProps) {
  const span = careerSpan(player.history)
  const best = bestRank(player.history)
  // Rated as soon as the player has a display rating (a single rated contest).
  const hasRating = player.rating !== null

  return (
    <header className="player-header">
      <p className="text-eyebrow">选手档案</p>
      <h1 className="player-header__name">{player.name}</h1>
      <p className="player-header__org text-muted">{player.org || '—'}</p>

      <div className="player-scores">
        <div className="player-score player-score--c">
          <span className="player-score__tag">阶梯分</span>
          <span className="player-score__value tnum">
            {hasRating ? formatScore(player.rating) : '—'}
          </span>
          {/* The hint only survives as the unrated fallback, which a single
              rated contest already clears, so it is effectively never shown. */}
          {hasRating ? null : (
            <span className="player-score__hint tnum">场次不足</span>
          )}
        </div>
      </div>

      <dl className="player-meta">
        <Metric label="参赛场次" value={player.contests} />
        <Metric label="最佳名次" value={best === null ? '—' : `第 ${best}`} />
        <Metric
          label="生涯跨度"
          value={formatDate(span.firstAt)}
          sub={`至 ${formatDate(span.lastAt)}`}
        />
      </dl>

      <PlayerMedalsBlock medals={player.medals} />
    </header>
  )
}

export default PlayerHeader
