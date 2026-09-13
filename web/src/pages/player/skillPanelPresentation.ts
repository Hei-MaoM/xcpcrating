import type { PlayerSkillAxis, PlayerSkillTier, SkillAxisKey } from '../../lib/data'
import { SKILL_AXIS_ORDER } from '../../lib/data'

export type SkillAxisState = 'ready' | 'missing'

/** Resolve the panel mode from the dossier's existing board caliber switch. */
export function skillPanelMode(official: boolean): 'all' | 'official' {
  return official ? 'official' : 'all'
}

/**
 * Keep the top one percent actionable: rounded percentiles collapse several
 * leaders to the same value, so use the exact competition rank when it is
 * available. Older bundles without a rank continue to show the percentile.
 */
export function formatSkillPercent(
  value: number | null | undefined,
  rank?: number | null,
): string {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return '暂无数据'
  }
  if (value <= 1 && typeof rank === 'number' && Number.isFinite(rank) && rank >= 1) {
    return `第 ${Math.round(rank)} 名`
  }
  return `同级前 ${value.toFixed(value < 1 ? 2 : 1)}%`
}

/** Stable message for absent contracts versus a player without a computed panel. */
export function skillPanelEmptyMessage(
  hasPanelContract: boolean,
  official: boolean,
): string {
  if (!hasPanelContract) {
    return '当前数据包尚未包含题型能力统计，重新导出 2023 年以来的题型 manifest 后即可显示。'
  }
  return `该选手暂无可用于题型能力统计的${official ? '正式参赛' : '全部参赛'}记录。`
}

/** Distinguish an absent axis from one with a computed metric. */
export function skillAxisStatus(
  metric: PlayerSkillAxis | undefined,
): SkillAxisState {
  if (!metric) return 'missing'
  if (
    metric.score === null &&
    metric.mastery === null &&
    metric.uniqueProblems === 0 &&
    metric.exposureWeight === 0
  ) {
    return 'missing'
  }
  return metric.score !== null && metric.topPercent !== null && metric.rankEligible !== false
    ? 'ready'
    : 'missing'
}

export function skillAxisRating(metric: PlayerSkillAxis | undefined): number | null {
  if (!metric) return null
  if (typeof metric.ability === 'number' && Number.isFinite(metric.ability)) return metric.ability
  if (metric.score !== null && Number.isFinite(metric.score)) return metric.score
  return null
}

/**
 * Rank calibration of the seven-axis radar.
 *
 * The radar plots each dimension by the player's standing in that dimension's
 * own leaderboard rather than by the raw rating, so 第 1 名 always fills the
 * outer ring and the remaining dimensions shrink only slightly:
 *
 *   第 1 名  -> 100%          (the outer ring)
 *   第 7 名  -> ~96%          ("稍微少一点")
 *   前 1%    -> 88%           (still the outermost band)
 *   前 5%    -> ~64%
 *   前 20%   -> ~44%
 *   末位     -> 20%
 *
 * The band edges come from the real cohort: the median axis cohort is ≈47.6k
 * ranked players, so 前 1% ≈ rank 476. Decay is logarithmic in the rank, which
 * keeps the elite band readable while still separating the middle of the field.
 */
const RADAR_TOP_RANK = 476
const RADAR_TAIL_RANK = 47600
const RADAR_TOP_BAND = 12
const RADAR_FLOOR = 20

/** Percentile band edges drawn as grid rings. */
const RADAR_RING_PERCENTILES: readonly { label: string; rank: number }[] = [
  { label: '第1名', rank: 1 },
  { label: '前1%', rank: RADAR_TOP_RANK },
  { label: '前5%', rank: Math.round(RADAR_TAIL_RANK * 0.05) },
  { label: '前20%', rank: Math.round(RADAR_TAIL_RANK * 0.2) },
]

/** Radius (percent) that one field rank occupies on the radar. */
export function skillRankStrength(rank: number | null | undefined): number | null {
  if (typeof rank !== 'number' || !Number.isFinite(rank) || rank < 1) return null
  if (rank <= 1) return 100
  if (rank <= RADAR_TOP_RANK) {
    return 100 - (RADAR_TOP_BAND * Math.log(rank)) / Math.log(RADAR_TOP_RANK)
  }
  const tail = Math.min(
    1,
    Math.log(rank / RADAR_TOP_RANK) / Math.log(RADAR_TAIL_RANK / RADAR_TOP_RANK),
  )
  return 100 - RADAR_TOP_BAND - (100 - RADAR_TOP_BAND - RADAR_FLOOR) * tail
}

/**
 * Seven-axis radar scale, driven by each dimension's field rank.
 *
 * A dimension without a published rank falls back to its share of the player's
 * best rating, so the chart still renders for partial records.
 */
export function skillRadarScale(panel: PlayerSkillTier) {
  const ratings = SKILL_AXIS_ORDER.map((axis) => skillAxisRating(panel.axes[axis]))
  const ranks = SKILL_AXIS_ORDER.map((axis) => panel.axes[axis]?.rank ?? null)
  const peak = Math.max(0, ...ratings.map((value) => value ?? 0))
  const strengths = SKILL_AXIS_ORDER.map((_axis, index) => {
    const byRank = skillRankStrength(ranks[index])
    if (byRank !== null) return byRank
    const rating = ratings[index]
    if (rating === null || peak <= 0) return null
    return Math.min(100, (rating / peak) * 100)
  })
  return {
    ratings,
    ranks,
    strengths,
    levels: RADAR_RING_PERCENTILES.map((band) => ({
      label: band.label,
      value: skillRankStrength(band.rank) ?? 100,
    })),
  }
}

/** Sort the seven dimensions by the player's score, with missing values last. */
export function sortSkillAxes(panel: PlayerSkillTier): SkillAxisKey[] {
  return [...SKILL_AXIS_ORDER].sort((left, right) => {
    const leftScore = skillAxisRating(panel.axes[left])
    const rightScore = skillAxisRating(panel.axes[right])
    if (leftScore === null && rightScore === null) return 0
    if (leftScore === null) return 1
    if (rightScore === null) return -1
    return rightScore - leftScore
  })
}

/** Put the selected dimension first while retaining score order for the rest. */
export function orderedSkillAxes(
  panel: PlayerSkillTier,
  selected: SkillAxisKey,
): SkillAxisKey[] {
  return [selected, ...sortSkillAxes(panel).filter((axis) => axis !== selected)]
}
