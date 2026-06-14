import type { MedalTier, PlayerMedals } from '../../lib/data'
import { medalTierRows, type MedalTierRow } from './stats'

interface PlayerMedalsProps {
  medals: PlayerMedals | undefined
}

/** Chinese tier labels in the export's tier vocabulary. */
const TIER_LABEL: Record<MedalTier, string> = {
  final: '决赛',
  regional: '区域赛',
  invitational: '邀请赛',
  provincial: '省赛',
}

/** One medal color's count chip, dimmed to a dot when the count is zero. */
function MedalChip({
  color,
  label,
  count,
}: {
  color: 'gold' | 'silver' | 'bronze'
  label: string
  count: number
}) {
  const empty = count === 0
  return (
    <span
      className={`medal-chip medal-chip--${color}${empty ? ' is-empty' : ''}`}
      title={`${label} ${count}`}
    >
      <span className="medal-chip__dot" aria-hidden="true" />
      <span className="medal-chip__label">{label}</span>
      <span className="medal-chip__count tnum">{count}</span>
    </span>
  )
}

/** A single tier's row: tier name on the left, three medal chips on the right. */
function TierRow({ row }: { row: MedalTierRow }) {
  const { tier, counts } = row
  return (
    <div className="player-medals__row">
      <span className="player-medals__tier">{TIER_LABEL[tier]}</span>
      <span className="player-medals__chips">
        <MedalChip color="gold" label="金" count={counts.gold} />
        <MedalChip color="silver" label="银" count={counts.silver} />
        <MedalChip color="bronze" label="铜" count={counts.bronze} />
      </span>
    </div>
  )
}

/**
 * The player's award block. One row per tier the player medaled in
 * (final / regional / invitational / provincial), in prestige order; zero-medal
 * tiers are dropped. Each row shows 金×N 银×N 铜×N with the award's own
 * semantic color as a restrained dot. A medal-less player renders a single em
 * dash, never an empty grid.
 */
export function PlayerMedalsBlock({ medals }: PlayerMedalsProps) {
  const rows = medalTierRows(medals)

  return (
    <section className="player-medals" aria-labelledby="medals-label">
      <span id="medals-label" className="player-medals__label">
        获奖
      </span>
      {rows.length === 0 ? (
        <span className="player-medals__empty">—</span>
      ) : (
        <div className="player-medals__rows">
          {rows.map((row) => (
            <TierRow key={row.tier} row={row} />
          ))}
        </div>
      )}
    </section>
  )
}

export default PlayerMedalsBlock
