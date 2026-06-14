import { useEffect, useMemo, useRef } from 'react'
// On-demand ECharts: register ONLY the pieces this chart uses, never the full
// bundle. Light Luxury direction — hairline grid, thin strokes, oxford ladder
// line + gold performance scatter, token-matched Simplified-Chinese tooltip.
import * as echarts from 'echarts/core'
import { LineChart, ScatterChart } from 'echarts/charts'
import {
  GridComponent,
  TooltipComponent,
  LegendComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import type { PlayerHistoryEntry } from '../../lib/data'
import { sortedByTime } from '../../pages/player/stats'

echarts.use([
  LineChart,
  ScatterChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  CanvasRenderer,
])

/* ------------------------------------------------------------------ *
 * Palette — resolved from the Light Luxury tokens so the chart matches
 * the rest of the site. Oxford-blue ladder line, gold perf scatter,
 * cool hairlines/ink.
 * ------------------------------------------------------------------ */
const COLOR = {
  oxford: 'oklch(37% 0.072 252)',
  gold: 'oklch(58% 0.098 78)',
  goldFill: 'oklch(70% 0.108 82 / 0.16)',
  ink: 'oklch(26% 0.013 258)',
  inkMuted: 'oklch(60% 0.009 256)',
  hairline: 'oklch(90% 0.005 252)',
  surface: 'oklch(99.5% 0.0025 252)',
} as const

const SANS = "'Noto Sans SC', -apple-system, sans-serif"
const SERIF = "'Noto Serif SC', serif"

const MIN_POINTS = 2

interface RatingChartProps {
  history: PlayerHistoryEntry[]
  /**
   * Terminal display ladder rating. Null when the player is unrated — in that
   * case the ladder line is omitted (only the perf scatter is drawn).
   */
  rating: number | null
}

function prefersReducedMotion(): boolean {
  return (
    typeof window !== 'undefined' &&
    typeof window.matchMedia === 'function' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches
  )
}

/**
 * Build the full ECharts option from a player's time-ordered history. One story:
 * the ladder's internal-expectation (E) evolution (oxford line) and the raw
 * per-contest performance scatter (gold). Pure helper, trivial to reason about.
 */
function buildOption(
  rows: PlayerHistoryEntry[],
  rating: number | null,
): echarts.EChartsCoreOption {
  const times = rows.map((h) => Date.parse(h.startAt))
  const perfPoints = rows.map((h, i) => [times[i], h.perf])

  const ladderLine =
    rating === null
      ? []
      : rows.flatMap((h, i) => (h.mu_after === null ? [] : [[times[i], h.mu_after]]))
  const hasLadderLine = ladderLine.length > 0

  return {
    animation: !prefersReducedMotion(),
    animationDuration: 700,
    animationDelay: (idx: number) => idx * 55,
    textStyle: { fontFamily: SANS, color: COLOR.ink },
    grid: { top: 48, right: 16, bottom: 32, left: 52 },
    legend: {
      top: 8,
      right: 4,
      icon: 'circle',
      itemWidth: 8,
      itemHeight: 8,
      textStyle: { fontSize: 12, color: COLOR.inkMuted, fontFamily: SANS },
      data: ['表现分', ...(hasLadderLine ? ['阶梯分'] : [])],
    },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'line', lineStyle: { color: COLOR.hairline } },
      backgroundColor: COLOR.surface,
      borderColor: COLOR.hairline,
      borderWidth: 1,
      padding: [12, 14],
      textStyle: { color: COLOR.ink, fontSize: 12, fontFamily: SANS },
      formatter: (params: unknown) => {
        const arr = Array.isArray(params) ? params : [params]
        const first = arr[0] as { axisValue?: number | string | Date } | undefined
        const ts = first?.axisValue == null ? NaN : Number(new Date(first.axisValue))
        const idx = times.findIndex((t) => t === ts)
        if (idx < 0) return ''
        const h = rows[idx]
        const champ = h.rank === 1
        const ladderTip =
          rating === null || h.mu_after === null
            ? ''
            : `<div style="color:${COLOR.oxford}">赛后分：${h.mu_after.toFixed(1)}</div>`
        return [
          `<div style="font-family:${SERIF};font-weight:600;max-width:18rem;white-space:normal">${
            champ ? '🥇 ' : ''
          }${h.title}</div>`,
          `<div style="color:${COLOR.inkMuted};margin-bottom:4px">${formatTip(
            h.startAt,
          )} · ${h.teamName}</div>`,
          `<div>名次：第 ${h.rank} / ${h.teamCount}</div>`,
          `<div>表现分：<b>${h.perf.toFixed(1)}</b></div>`,
          ladderTip,
        ].join('')
      },
    },
    xAxis: {
      type: 'time',
      axisLine: { lineStyle: { color: COLOR.hairline } },
      axisTick: { show: false },
      axisLabel: { color: COLOR.inkMuted, fontSize: 11, hideOverlap: true },
      splitLine: { show: false },
    },
    yAxis: {
      type: 'value',
      scale: true,
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: COLOR.inkMuted, fontSize: 11 },
      splitLine: { lineStyle: { color: COLOR.hairline, type: 'solid' } },
    },
    series: [
      {
        name: '表现分',
        type: 'scatter',
        data: perfPoints,
        symbolSize: 8,
        z: 3,
        itemStyle: {
          color: COLOR.goldFill,
          borderColor: COLOR.gold,
          borderWidth: 1.8,
        },
      },
      ...(hasLadderLine
        ? [
            {
              name: '阶梯分',
              type: 'line' as const,
              data: ladderLine,
              smooth: 0.35,
              showSymbol: false,
              connectNulls: true,
              z: 2,
              lineStyle: { color: COLOR.oxford, width: 2 },
              areaStyle: { color: 'oklch(37% 0.072 252 / 0.08)' },
              emphasis: { disabled: true },
            },
          ]
        : []),
    ],
  }
}

const TIP_FMT = new Intl.DateTimeFormat('zh-CN', {
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
})

function formatTip(iso: string): string {
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? '—' : TIP_FMT.format(d)
}

/**
 * Performance-score trajectory chart. Renders a self-resizing ECharts canvas
 * (perf scatter + ladder line). Falls back to an elegant "insufficient data"
 * empty state when the player has fewer than two contests.
 */
export function RatingChart({ history, rating }: RatingChartProps) {
  const ref = useRef<HTMLDivElement>(null)
  const rows = useMemo(() => sortedByTime(history), [history])

  useEffect(() => {
    const el = ref.current
    if (!el || rows.length < MIN_POINTS) return

    const chart = echarts.init(el)
    chart.setOption(buildOption(rows, rating))

    const onResize = () => chart.resize()
    window.addEventListener('resize', onResize)
    return () => {
      window.removeEventListener('resize', onResize)
      chart.dispose()
    }
  }, [rows, rating])

  if (rows.length < MIN_POINTS) {
    return (
      <div className="chart-empty" role="img" aria-label="数据不足">
        <p className="chart-empty__title">数据不足</p>
        <p className="chart-empty__hint">
          该选手仅有 {rows.length} 场记录，至少需要 2 场才能绘制表现分轨迹。
        </p>
      </div>
    )
  }

  return (
    <div
      ref={ref}
      className="chart-box"
      role="img"
      aria-label="选手表现分轨迹图：金点为每场表现分，蓝线为阶梯分演化"
    />
  )
}

export default RatingChart
