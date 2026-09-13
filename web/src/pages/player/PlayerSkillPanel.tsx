import { Reveal, RuleDraw } from '../../components/ui'
import type {
  PanelScope,
  PlayerDetail,
  PlayerSkillAxis,
  PlayerSkillTier,
  SkillAxisKey,
} from '../../lib/data'
import {
  SKILL_AXIS_LABELS,
  SKILL_AXIS_ORDER,
} from '../../lib/data'
import { GradeBadge } from '../../components/ui/GradeBadge'
import { radarPointString, radarPoints } from './radarGeometry'
import { formatSkillPercent, skillAxisRating, skillAxisStatus, skillPanelMode, skillRadarScale, sortSkillAxes } from './skillPanelPresentation'
import './player-metrics.css'

const TIER_ORDER: readonly PanelScope[] = ['overall']

const RADAR_CENTER_X = 180
const RADAR_CENTER_Y = 136
const RADAR_RADIUS = 88
const RADAR_LABEL_RADIUS = 122

function SkillRadar({ tier, panel }: { tier: PanelScope; panel: PlayerSkillTier }) {
  const { strengths, ratings, ranks, levels } = skillRadarScale(panel)
  const outer = radarPoints(
    SKILL_AXIS_ORDER.map(() => 100),
    RADAR_RADIUS,
    RADAR_CENTER_X,
    RADAR_CENTER_Y,
  )
  const labels = radarPoints(
    SKILL_AXIS_ORDER.map(() => 100),
    RADAR_LABEL_RADIUS,
    RADAR_CENTER_X,
    RADAR_CENTER_Y,
  )
  const titleId = `skill-radar-title-${tier}`
  const summary = SKILL_AXIS_ORDER.map((axis, index) => {
    const rating = ratings[index]
    const rank = ranks[index]
    if (rating === null) return `${SKILL_AXIS_LABELS[axis]}：暂无数据`
    const standing = typeof rank === 'number' && rank >= 1 ? `（第 ${Math.round(rank)} 名）` : ''
    return `${SKILL_AXIS_LABELS[axis]}：${rating.toFixed(1)} 分${standing}`
  }).join('；')

  return (
    <figure className="skill-radar">
      <svg className="skill-radar__svg" viewBox="0 0 360 270" role="img" aria-labelledby={titleId}>
        <title id={titleId}>总体题型能力七边形。{summary}</title>
        <g aria-hidden="true">
          {levels.map((level, index) => (
            <polygon
              key={`ring-${index}`}
              className={`skill-radar__grid ${level.value === 100 ? 'skill-radar__grid--outer' : ''}`}
              points={radarPointString(radarPoints(SKILL_AXIS_ORDER.map(() => level.value), RADAR_RADIUS, RADAR_CENTER_X, RADAR_CENTER_Y))}
            />
          ))}
          {outer.map((point, index) => (
            <line
              key={SKILL_AXIS_ORDER[index]}
              className="skill-radar__spoke"
              x1={RADAR_CENTER_X}
              y1={RADAR_CENTER_Y}
              x2={point.x}
              y2={point.y}
            />
          ))}
        </g>
        <polygon className="skill-radar__shape" points={radarPointString(radarPoints(strengths, RADAR_RADIUS, RADAR_CENTER_X, RADAR_CENTER_Y))} aria-hidden="true" />
        {radarPoints(strengths, RADAR_RADIUS, RADAR_CENTER_X, RADAR_CENTER_Y).map((point, index) => (
          <circle
            key={SKILL_AXIS_ORDER[index]}
            className={`skill-radar__point ${strengths[index] === null ? 'skill-radar__point--missing' : ''}`}
            cx={point.x}
            cy={point.y}
            r="3.8"
            aria-hidden="true"
          />
        ))}
        {labels.map((point, index) => {
          const anchor = Math.abs(point.x - RADAR_CENTER_X) < 8 ? 'middle' : point.x > RADAR_CENTER_X ? 'start' : 'end'
          const shift = point.y < RADAR_CENTER_Y ? -2 : 5
          return (
            <text key={SKILL_AXIS_ORDER[index]} className="skill-radar__label" x={point.x} y={point.y + shift} textAnchor={anchor} aria-hidden="true">
              {SKILL_AXIS_LABELS[SKILL_AXIS_ORDER[index]]}
            </text>
          )
        })}
      </svg>
      <figcaption className="skill-radar__caption">
        按各维度全场名次绘制 · 第 1 名满格 · 前 1% 约 {(levels[1]?.value ?? 88).toFixed(0)}%
      </figcaption>
    </figure>
  )
}

function AxisSummary({
  axis,
  metric,
  rank,
}: {
  axis: SkillAxisKey
  metric: PlayerSkillAxis | undefined
  rank: number
}) {
  const rating = skillAxisRating(metric)
  const score = rating === null ? '暂无数据' : rating.toFixed(1)
  const status = skillAxisStatus(metric)
  const top = status === 'ready' ? formatSkillPercent(metric?.topPercent, metric?.rank) : '暂无数据'
  return (
    <div
      className="skill-axis"
      title={`${SKILL_AXIS_LABELS[axis]}：与题目 rating 同尺度的原始能力分`}
    >
      <div className="skill-axis__head">
        <span className="skill-axis__label">
          <span className="skill-axis__rank tnum">#{rank}</span>
          {SKILL_AXIS_LABELS[axis]}
        </span>
        <GradeBadge grade={status === 'ready' ? metric?.grade ?? null : null} emptyText="暂无数据" />
      </div>
      <div className="skill-axis__body">
        <span className="skill-axis__score tnum">{score}</span>
        <span className="skill-axis__percent tnum">{top}</span>
      </div>
    </div>
  )
}

function SkillTierCard({
  tier,
  panel,
  delay,
}: {
  tier: PanelScope
  panel: PlayerSkillTier | undefined
  delay: number
}) {
  return (
    <Reveal className={`skill-tier-card ${panel ? '' : 'skill-tier-card--empty'}`} delay={delay}>
      <div className="skill-tier-card__head">
        <div>
          <h3 className="skill-tier-card__title serif">总体能力</h3>
          <p className="skill-tier-card__summary">
            {panel ? `${panel.contests} 场参赛` : '暂无数据'}
          </p>
        </div>
        {panel ? <span className="skill-tier-card__version">{panel.taxonomyVersion}</span> : null}
      </div>
      {panel ? (
        <div className="skill-tier-card__body">
          <SkillRadar tier={tier} panel={panel} />
          <div className="skill-axis-grid">
            {sortSkillAxes(panel).map((axis) => (
              <AxisSummary
                key={axis}
                axis={axis}
                metric={panel.axes[axis]}
                rank={sortSkillAxes(panel).indexOf(axis) + 1}
              />
            ))}
          </div>
        </div>
      ) : (
        <div className="skill-tier-card__blank">暂无数据</div>
      )}
    </Reveal>
  )
}

export function PlayerSkillPanel({ player, official }: { player: PlayerDetail; official: boolean }) {
  const mode = skillPanelMode(official)
  const panels = player.skillPanel?.[mode]
  const hasData = TIER_ORDER.some((tier) => Boolean(panels?.[tier]))
  return (
    <section className="wrap skill-panel" aria-labelledby="skill-panel-title">
      <div className="skill-panel__heading">
        <div className="section-label">
          <span id="skill-panel-title" className="eyebrow">题型能力七维</span>
          <RuleDraw className="section-label__rule" />
        </div>
        <p className="skill-panel__caption">2025+ 题面/题解分类 · 按题目预期通过率校准 · 当前为{official ? '正式参赛' : '全部参赛'}口径</p>
      </div>
      {hasData ? (
        <div className="skill-panel__grid">
          {TIER_ORDER.map((tier, index) => (
            <SkillTierCard
              key={tier}
              tier={tier}
              panel={panels?.[tier]}
              delay={index * 55}
            />
          ))}
        </div>
      ) : (
        <div className="skill-panel__empty">暂无数据</div>
      )}
    </section>
  )
}
