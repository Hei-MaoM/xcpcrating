import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Caret, Reveal } from '../../components/ui'
import {
  getContestsIndex,
  type ContestIndexEntry,
} from '../../lib/data'
import { formatDate, formatPercent } from '../../lib/format'
import { ContestSectionNav } from '../contests/ContestSectionNav'
import {
  ALL_COMPETITION_SEASONS,
  listCompetitionSeasons,
  resolveCompetitionSeason,
  serializeCompetitionSeason,
  type CompetitionSeason,
} from '../contests/competition-season'
import {
  CONTEST_TIER_FILTERS,
  buildContestRanking,
  contestCategoryBadgeLabel,
  contestTierLabel,
  isContestRankingMetric,
  parseContestTierSelection,
  serializeContestTierSelection,
  toggleContestTier,
  type ContestRankingMetric,
  type ContestRankingTier,
} from './ranking'
import './contest-rankings.css'

interface MetricDefinition {
  label: string
  shortLabel: string
  family: string
  eyebrow: string
  description: string
}

const DEFAULT_METRIC: ContestRankingMetric = 'overall'

const METRIC_ORDER: readonly ContestRankingMetric[] = [
  'bronze',
  'silver',
  'gold',
  'top3',
  'top10',
  'overall',
]

const METRIC_DEFINITIONS: Record<ContestRankingMetric, MetricDefinition> = {
  bronze: {
    label: '铜牌难度',
    shortLabel: '铜牌',
    family: '奖牌门槛',
    eyebrow: 'Bronze threshold',
    description: '进入累计铜牌线所需的真实赛前阵容分。',
  },
  silver: {
    label: '银牌难度',
    shortLabel: '银牌',
    family: '奖牌门槛',
    eyebrow: 'Silver threshold',
    description: '进入累计银牌线所需的真实赛前阵容分。',
  },
  gold: {
    label: '金牌难度',
    shortLabel: '金牌',
    family: '奖牌门槛',
    eyebrow: 'Gold threshold',
    description: '进入金牌线所需的真实赛前阵容分。',
  },
  top3: {
    label: '前三难度',
    shortLabel: '前三',
    family: '前列门槛',
    eyebrow: 'Top three',
    description: '进入正式队伍前三所需的真实赛前阵容分。',
  },
  top10: {
    label: '前十难度',
    shortLabel: '前十',
    family: '前列门槛',
    eyebrow: 'Top ten',
    description: '进入正式队伍前十所需的真实赛前阵容分。',
  },
  overall: {
    label: '整体难度',
    shortLabel: '整体',
    family: '全场阵容',
    eyebrow: 'Field strength',
    description: '所有正式参赛队伍赛前阵容分的等权均值。',
  },
  weirdness: {
    label: '怪异分',
    shortLabel: '怪异',
    family: '赛果偏差',
    eyebrow: 'Prediction surprise',
    description: '仅比较三名队员都有赛前历史的队伍；前列错位权重更高，并按完整历史覆盖率折减。',
  },
}

function readMetric(value: string | null): ContestRankingMetric {
  return isContestRankingMetric(value) && METRIC_ORDER.includes(value)
    ? value
    : DEFAULT_METRIC
}

function RankMark({ rank }: { rank: number }) {
  const podiumClass = rank <= 3 ? ` cr-rank--${rank}` : ''
  return (
    <span className={`cr-rank${podiumClass}`} aria-label={`第 ${rank} 名`}>
      {rank}
    </span>
  )
}

function ContestCategory({ contest }: { contest: ContestIndexEntry }) {
  const { category } = contest
  const tone =
    category === 'icpc' ? 'icpc' : category === 'ccpc' ? 'ccpc' : 'prov'
  return (
    <span className={`badge badge--${tone}`}>
      {contestCategoryBadgeLabel(contest)}
    </span>
  )
}

function WeirdnessSample({
  contest,
  compact = false,
}: {
  contest: ContestIndexEntry
  compact?: boolean
}) {
  const metrics = contest.contestMetrics
  const count = metrics?.weirdnessTeamCount ?? 0
  return compact ? (
    <>
      {count} 支完整历史队伍
      <span aria-hidden="true"> · </span>
      覆盖 {formatPercent(metrics?.historyCoverage)}
    </>
  ) : (
    <>
      <strong>{count}</strong>
      <span>
        支完整历史队伍 · 覆盖 {formatPercent(metrics?.historyCoverage)}
      </span>
    </>
  )
}

interface ContestTierPickerProps {
  selectedTiers: ReadonlyArray<ContestRankingTier>
  counts: Record<ContestRankingTier, number>
  totalCount: number
  onClear: () => void
  onToggle: (tier: ContestRankingTier) => void
}

function ContestTierPicker({
  selectedTiers,
  counts,
  totalCount,
  onClear,
  onToggle,
}: ContestTierPickerProps) {
  const [open, setOpen] = useState(false)
  const pickerRef = useRef<HTMLDivElement>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const selectedNames = selectedTiers.map((tier) => contestTierLabel(tier))
  const selectionLabel =
    selectedNames.length === 0
      ? '全部类别'
      : selectedNames.length <= 2
        ? selectedNames.join('、')
        : `已选 ${selectedNames.length} 类`

  useEffect(() => {
    if (!open) return

    function closeOnOutside(event: PointerEvent) {
      if (
        event.target instanceof Node &&
        !pickerRef.current?.contains(event.target)
      ) {
        setOpen(false)
      }
    }

    function closeOnEscape(event: KeyboardEvent) {
      if (event.key !== 'Escape') return
      setOpen(false)
      triggerRef.current?.focus()
    }

    document.addEventListener('pointerdown', closeOnOutside)
    document.addEventListener('keydown', closeOnEscape)
    return () => {
      document.removeEventListener('pointerdown', closeOnOutside)
      document.removeEventListener('keydown', closeOnEscape)
    }
  }, [open])

  return (
    <div className="cr-tier-picker" ref={pickerRef}>
      <button
        ref={triggerRef}
        type="button"
        className="cr-tier-trigger"
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-controls="contest-tier-menu"
        onClick={() => setOpen((value) => !value)}
      >
        <span className="cr-tier-trigger__icon" aria-hidden="true">
          <i />
          <i />
          <i />
        </span>
        <span className="cr-tier-trigger__copy">
          <strong>{selectionLabel}</strong>
        </span>
        <Caret dir={open ? 'up' : 'down'} size={13} />
      </button>

      {open ? (
        <div
          className="cr-tier-menu"
          id="contest-tier-menu"
          role="dialog"
          aria-label="选择比赛类别"
        >
          <div className="cr-tier-menu__head">
            <div>
              <strong>筛选比赛类别</strong>
              <span>可同时选择多个类别</span>
            </div>
            <button type="button" onClick={() => setOpen(false)}>
              完成
            </button>
          </div>

          <div className="cr-tier-options" role="group" aria-label="比赛类别">
            <button
              type="button"
              className={`cr-tier-option${selectedTiers.length === 0 ? ' is-active' : ''}`}
              aria-pressed={selectedTiers.length === 0}
              onClick={onClear}
            >
              <span className="cr-tier-option__check" aria-hidden="true">
                {selectedTiers.length === 0 ? '✓' : ''}
              </span>
              <span className="cr-tier-option__label">全部类别</span>
              <span className="cr-tier-option__count tnum">{totalCount}</span>
            </button>

            {CONTEST_TIER_FILTERS.map((tier) => {
              const selected = selectedTiers.includes(tier)
              return (
                <button
                  key={tier}
                  type="button"
                  className={`cr-tier-option${selected ? ' is-active' : ''}`}
                  aria-pressed={selected}
                  onClick={() => onToggle(tier)}
                >
                  <span className="cr-tier-option__check" aria-hidden="true">
                    {selected ? '✓' : ''}
                  </span>
                  <span className="cr-tier-option__label">
                    {contestTierLabel(tier)}
                  </span>
                  <span className="cr-tier-option__count tnum">
                    {counts[tier]}
                  </span>
                </button>
              )
            })}
          </div>

          <p className="cr-tier-menu__foot">
            右侧数字为当前指标、当前赛季可排行的比赛数
          </p>
        </div>
      ) : null}
    </div>
  )
}

interface ContestSeasonPickerProps {
  seasons: ReadonlyArray<CompetitionSeason>
  selectedSeason: string
  counts: Readonly<Record<string, number>>
  onSelect: (season: string) => void
}

function ContestSeasonPicker({
  seasons,
  selectedSeason,
  counts,
  onSelect,
}: ContestSeasonPickerProps) {
  const selected = seasons.find((season) => season.key === selectedSeason)
  const allSelected = selectedSeason === ALL_COMPETITION_SEASONS
  const shortYear = allSelected
    ? '全'
    : selected
      ? String(selected.startYear).slice(-2).padStart(2, '0')
      : '—'

  return (
    <div className="cr-season-picker">
      <span className="cr-season-picker__icon tnum" aria-hidden="true">
        {shortYear}
      </span>
      <span className="cr-tier-trigger__copy">
        <strong>
          {allSelected ? '全部赛季' : (selected?.label ?? '暂无赛季')}
        </strong>
      </span>
      <Caret dir="down" size={13} />
      <select
        aria-label="选择竞赛赛季"
        value={selectedSeason}
        onChange={(event) => onSelect(event.target.value)}
      >
        <option value={ALL_COMPETITION_SEASONS}>
          全部赛季 · {counts[ALL_COMPETITION_SEASONS] ?? 0} 场
        </option>
        {seasons.map((season) => (
          <option key={season.key} value={season.key}>
            {season.label} · {counts[season.key] ?? 0} 场
          </option>
        ))}
      </select>
    </div>
  )
}

export default function ContestRankingsPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [contests, setContests] = useState<ContestIndexEntry[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  const rawMetricParam = searchParams.get('metric')
  const metric = readMetric(rawMetricParam)
  const canonicalMetricParam = metric === DEFAULT_METRIC ? null : metric
  const rawTierParam = searchParams.get('tier')
  const selectedTiers = useMemo(
    () => parseContestTierSelection(rawTierParam),
    [rawTierParam],
  )
  const canonicalTierParam = serializeContestTierSelection(selectedTiers)
  const seasons = useMemo(
    () => (contests ? listCompetitionSeasons(contests) : []),
    [contests],
  )
  const rawSeasonParam = searchParams.get('season')
  const selectedSeason = resolveCompetitionSeason(seasons, rawSeasonParam)
  const canonicalSeasonParam = serializeCompetitionSeason(
    seasons,
    selectedSeason,
  )
  const selectedSeasonLabel =
    selectedSeason === ALL_COMPETITION_SEASONS
      ? '全部赛季'
      : (seasons.find((season) => season.key === selectedSeason)?.label ?? '—')
  const metricDefinition = METRIC_DEFINITIONS[metric]
  const metricPosition = METRIC_ORDER.indexOf(metric) + 1

  // Normalize shared/bookmarked URLs after the available seasons are known.
  useEffect(() => {
    if (contests === null) return
    if (
      rawTierParam === canonicalTierParam &&
      rawSeasonParam === canonicalSeasonParam &&
      rawMetricParam === canonicalMetricParam
    ) {
      return
    }
    const params = new URLSearchParams(searchParams)
    if (canonicalTierParam === null) params.delete('tier')
    else params.set('tier', canonicalTierParam)
    if (canonicalSeasonParam === null) params.delete('season')
    else params.set('season', canonicalSeasonParam)
    if (canonicalMetricParam === null) params.delete('metric')
    else params.set('metric', canonicalMetricParam)
    setSearchParams(params, { replace: true })
  }, [
    canonicalTierParam,
    canonicalMetricParam,
    canonicalSeasonParam,
    contests,
    rawSeasonParam,
    rawMetricParam,
    rawTierParam,
    searchParams,
    setSearchParams,
  ])

  useEffect(() => {
    let cancelled = false
    getContestsIndex()
      .then((data) => {
        if (!cancelled) setContests(data)
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : '加载失败')
        }
      })
    return () => {
      cancelled = true
    }
  }, [])

  const rows = useMemo(
    () =>
      contests
        ? buildContestRanking(contests, metric, selectedTiers, selectedSeason)
        : [],
    [contests, metric, selectedSeason, selectedTiers],
  )
  const tierCounts = useMemo(() => {
    const counts: Record<ContestRankingTier, number> = {
      final: 0,
      regional: 0,
      invitational: 0,
      provincial: 0,
      online: 0,
    }
    if (!contests) return counts
    for (const tier of CONTEST_TIER_FILTERS) {
      counts[tier] = buildContestRanking(
        contests,
        metric,
        [tier],
        selectedSeason,
      ).length
    }
    return counts
  }, [contests, metric, selectedSeason])
  const allTierCount = useMemo(
    () =>
      contests
        ? buildContestRanking(contests, metric, [], selectedSeason).length
        : 0,
    [contests, metric, selectedSeason],
  )
  const seasonCounts = useMemo(
    () =>
      Object.fromEntries([
        [
          ALL_COMPETITION_SEASONS,
          contests
            ? buildContestRanking(
                contests,
                metric,
                selectedTiers,
                ALL_COMPETITION_SEASONS,
              ).length
            : 0,
        ],
        ...seasons.map((season) => [
          season.key,
          contests
            ? buildContestRanking(
                contests,
                metric,
                selectedTiers,
                season.key,
              ).length
            : 0,
        ]),
      ]),
    [contests, metric, seasons, selectedTiers],
  )
  const showSample = metric === 'weirdness'

  function selectMetric(next: ContestRankingMetric) {
    const params = new URLSearchParams(searchParams)
    if (next === DEFAULT_METRIC) params.delete('metric')
    else params.set('metric', next)
    setSearchParams(params)
  }

  function clearTiers() {
    setSearchParams((previous) => {
      const params = new URLSearchParams(previous)
      params.delete('tier')
      return params
    })
  }

  function selectTier(nextTier: ContestRankingTier) {
    setSearchParams((previous) => {
      const params = new URLSearchParams(previous)
      const current = parseContestTierSelection(params.get('tier'))
      const next = toggleContestTier(current, nextTier)
      const serialized = serializeContestTierSelection(next)
      if (serialized === null) params.delete('tier')
      else params.set('tier', serialized)
      return params
    })
  }

  function selectSeason(nextSeason: string) {
    setSearchParams((previous) => {
      const params = new URLSearchParams(previous)
      if (nextSeason === ALL_COMPETITION_SEASONS) params.delete('season')
      else params.set('season', nextSeason)
      return params
    })
  }

  return (
    <div className="page-enter cr-page">
      <section className="wrap phead cr-head">
        <span className="eyebrow eyebrow--oxford">赛事指标档案</span>
        <h1 className="display">赛事指标榜</h1>
        <p className="subtle">
          难度仅供参考。
        </p>
        <ContestSectionNav />
      </section>

      <section className="wrap cr-controls" aria-label="排行榜筛选">
        <div className="cr-control-deck">
          <div className="cr-metric-summary" aria-live="polite">
            <div className="cr-metric-summary__topline">
              <span className="eyebrow">{metricDefinition.eyebrow}</span>
              <span className="cr-metric-summary__index tnum">
                {String(metricPosition).padStart(2, '0')} / {String(METRIC_ORDER.length).padStart(2, '0')}
              </span>
            </div>
            <div>
              <span className="cr-metric-summary__family">{metricDefinition.family}</span>
              <h2>{metricDefinition.label}</h2>
              <p>{metricDefinition.description}</p>
            </div>
          </div>

          <div className="cr-metric-switch" role="group" aria-label="选择排行指标">
            {METRIC_ORDER.map((item, index) => (
              <button
                key={item}
                type="button"
                className={`cr-metric-button${metric === item ? ' is-active' : ''}`}
                aria-pressed={metric === item}
                onClick={() => selectMetric(item)}
              >
                <span className="cr-metric-button__index tnum">
                  {String(index + 1).padStart(2, '0')}
                </span>
                <span className="cr-metric-button__copy">
                  <strong>{METRIC_DEFINITIONS[item].shortLabel}</strong>
                  <small>{METRIC_DEFINITIONS[item].family}</small>
                </span>
                <span className="cr-metric-button__mark" aria-hidden="true" />
              </button>
            ))}
          </div>

          <div className="cr-series-row">
            <div className="cr-filter-group">
              <span className="cr-filter-label">
                <strong>竞赛赛季</strong>
                <small>9/1—次年 8/31</small>
              </span>
              <ContestSeasonPicker
                seasons={seasons}
                selectedSeason={selectedSeason}
                counts={seasonCounts}
                onSelect={selectSeason}
              />
            </div>
            <div className="cr-filter-group">
              <span className="cr-filter-label">
                <strong>比赛类别</strong>
                <small>可多选</small>
              </span>
              <ContestTierPicker
                selectedTiers={selectedTiers}
                counts={tierCounts}
                totalCount={allTierCount}
                onClear={clearTiers}
                onToggle={selectTier}
              />
            </div>
          </div>
        </div>
      </section>

      {error ? (
        <div className="state" role="alert">
          <p className="state__title">排行榜加载失败</p>
          <p>{error}</p>
        </div>
      ) : contests === null ? (
        <div className="state" role="status">
          正在整理赛事指标…
        </div>
      ) : rows.length === 0 ? (
        <div className="state" role="status">
          <p className="state__title">暂无可排行的比赛</p>
          <p>当前赛季与类别中没有有效的{metricDefinition.label}数据。</p>
        </div>
      ) : (
        <section className="wrap cr-board" aria-labelledby="contest-ranking-title">
          <div className="cr-board-topline">
            <h2 id="contest-ranking-title">
              {selectedSeasonLabel} {metricDefinition.label}排行
            </h2>
            <span className="tnum">
              共 <strong>{rows.length}</strong> 场有效比赛
            </span>
          </div>

          <div
            className={`cr-row cr-row--head${showSample ? '' : ' cr-row--no-sample'}`}
            aria-hidden="true"
          >
            <span>名次</span>
            <span>比赛</span>
            {showSample ? <span>有效样本</span> : null}
            <span className="right">{metricDefinition.label}</span>
          </div>

          <ol className="cr-list" aria-label={`${metricDefinition.label}排行榜`}>
            {rows.map(({ contest, rank, score }, index) => (
              <Reveal
                as="li"
                className={`cr-row cr-entry${showSample ? '' : ' cr-row--no-sample'}`}
                delay={Math.min(index, 8) * 24}
                key={contest.slug}
              >
                <RankMark rank={rank} />

                <div className="cr-event">
                  <Link
                    className="cr-event__title"
                    to={`/contest/${contest.slug}`}
                  >
                    {contest.title}
                  </Link>
                  <div className="cr-event__meta">
                    <time dateTime={contest.startAt} className="tnum">
                      {formatDate(contest.startAt)}
                    </time>
                    <span aria-hidden="true">·</span>
                    <ContestCategory contest={contest} />
                    {showSample ? (
                      <span className="cr-event__mobile-sample">
                        <WeirdnessSample contest={contest} compact />
                      </span>
                    ) : null}
                  </div>
                </div>

                {showSample ? (
                  <div className="cr-sample tnum">
                    <WeirdnessSample contest={contest} />
                  </div>
                ) : null}

                <div className="cr-score tnum">
                  <div>
                    <strong>
                      {metric === 'weirdness'
                        ? score.toFixed(2)
                        : score.toFixed(1)}
                    </strong>
                    <span>
                      {metric === 'weirdness' ? '/ 100' : '赛前分'}
                    </span>
                  </div>
                  {metric === 'weirdness' ? (
                    <span className="cr-score__track" aria-hidden="true">
                      <span style={{ width: `${Math.max(0, Math.min(100, score))}%` }} />
                    </span>
                  ) : null}
                </div>
              </Reveal>
            ))}
          </ol>
        </section>
      )}
    </div>
  )
}
