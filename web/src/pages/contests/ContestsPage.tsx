import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { getContestsIndex, type ContestIndexEntry } from '../../lib/data'
import { formatDate, formatYear } from '../../lib/format'
import { Caret, Reveal } from '../../components/ui'
import {
  SERIES_FILTERS,
  categoryLabel,
  isSeriesFilter,
  seriesLabel,
  type SeriesFilter,
} from './categories'

/** Initial render budget; large archives reveal the rest via "load more". */
const INITIAL_VISIBLE = 60
const LOAD_MORE_STEP = 60

interface YearGroup {
  year: string
  contests: ContestIndexEntry[]
}

/** Category badge mapped to the Light Luxury palette (taxonomy, never medals). */
function CatBadge({ category }: { category: string }) {
  const cls =
    category === 'icpc' ? 'icpc' : category === 'ccpc' ? 'ccpc' : 'prov'
  return <span className={`badge badge--${cls}`}>{categoryLabel(category)}</span>
}

/** Filter by series, sort by date desc, group by year (years desc). */
function buildGroups(contests: ContestIndexEntry[], series: SeriesFilter): YearGroup[] {
  const filtered = contests.filter((c) => series === 'all' || c.category === series)
  const sorted = [...filtered].sort(
    (a, b) => new Date(b.startAt).getTime() - new Date(a.startAt).getTime(),
  )
  const groups: YearGroup[] = []
  let current: YearGroup | null = null
  for (const contest of sorted) {
    const year = formatYear(contest.startAt)
    if (!current || current.year !== year) {
      current = { year, contests: [] }
      groups.push(current)
    }
    current.contests.push(contest)
  }
  return groups
}

function countContests(groups: YearGroup[]): number {
  return groups.reduce((sum, g) => sum + g.contests.length, 0)
}

/** Truncate grouped contests to `limit` total rows, preserving year boundaries. */
function takeVisible(groups: YearGroup[], limit: number): { visible: YearGroup[]; hasMore: boolean } {
  const visible: YearGroup[] = []
  let remaining = limit
  for (const group of groups) {
    if (remaining <= 0) break
    const slice = group.contests.slice(0, remaining)
    visible.push({ year: group.year, contests: slice })
    remaining -= slice.length
  }
  const total = countContests(groups)
  return { visible, hasMore: countContests(visible) < total }
}

export default function ContestsPage() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()

  const series: SeriesFilter = isSeriesFilter(searchParams.get('series'))
    ? (searchParams.get('series') as SeriesFilter)
    : 'all'

  const [contests, setContests] = useState<ContestIndexEntry[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [visibleCount, setVisibleCount] = useState(INITIAL_VISIBLE)

  useEffect(() => {
    getContestsIndex()
      .then(setContests)
      .catch((err: unknown) => setError(err instanceof Error ? err.message : '加载失败'))
  }, [])

  // Reset the reveal budget whenever the series filter changes (during render).
  const [revealedFor, setRevealedFor] = useState(series)
  if (series !== revealedFor) {
    setRevealedFor(series)
    setVisibleCount(INITIAL_VISIBLE)
  }

  const groups = useMemo(() => (contests ? buildGroups(contests, series) : []), [contests, series])
  const totalMatches = useMemo(() => countContests(groups), [groups])
  const { visible, hasMore } = useMemo(() => takeVisible(groups, visibleCount), [groups, visibleCount])
  const shown = useMemo(() => countContests(visible), [visible])

  function selectSeries(next: SeriesFilter) {
    const params = new URLSearchParams(searchParams)
    if (next === 'all') params.delete('series')
    else params.set('series', next)
    setSearchParams(params)
  }

  return (
    <div className="page-enter">
      <section className="wrap phead">
        <span className="eyebrow eyebrow--oxford">赛事档案</span>
        <h1 className="display">比赛列表</h1>
        <p className="subtle">
          收录 ICPC、CCPC 与各省省赛共 {contests?.length ?? '—'} 场，按年份归档。
        </p>
      </section>

      <section className="wrap" style={{ paddingBottom: 40 }}>
        <div className="filterbar">
          <div className="chip-row" role="group" aria-label="按系列筛选">
            {SERIES_FILTERS.map((filter) => (
              <button
                key={filter}
                type="button"
                aria-pressed={series === filter}
                className={`chip ${series === filter ? 'is-active' : ''}`}
                onClick={() => selectSeries(filter)}
              >
                {seriesLabel(filter)}
              </button>
            ))}
          </div>
        </div>
      </section>

      {error ? (
        <div className="state" role="alert">
          <p className="state__title">加载失败</p>
          <p>{error}</p>
        </div>
      ) : contests === null ? (
        <div className="state" role="status">
          正在加载比赛档案…
        </div>
      ) : totalMatches === 0 ? (
        <div className="state" role="status">
          <p className="state__title">没有匹配的比赛</p>
          <p>试试切换系列。</p>
        </div>
      ) : (
        <>
          <section className="wrap" style={{ paddingBottom: 24 }}>
            {visible.map((group) => (
              <div className="ygroup" key={group.year}>
                <div className="ygroup__marker">
                  <span className="ygroup__year serif">{group.year}</span>
                  <span className="ygroup__count">{group.contests.length} 场</span>
                </div>
                <div className="clist">
                  {group.contests.map((c) => (
                    <Reveal
                      as="div"
                      className="crow"
                      key={c.slug}
                      role="link"
                      tabIndex={0}
                      onClick={() => navigate(`/contest/${c.slug}`)}
                      onKeyDown={(e) => e.key === 'Enter' && navigate(`/contest/${c.slug}`)}
                    >
                      <span className="crow__date tnum">{formatDate(c.startAt)}</span>
                      <span className="crow__title">{c.title}</span>
                      <span className="crow__cat">
                        <CatBadge category={c.category} />
                      </span>
                      <span className="crow__teams tnum">
                        <b>{c.teamCount}</b> 队
                      </span>
                      <span className="crow__go">
                        <Caret dir="right" size={13} />
                      </span>
                    </Reveal>
                  ))}
                </div>
              </div>
            ))}
          </section>

          {hasMore ? (
            <div className="wrap">
              <div className="loadmore">
                <button className="btn" onClick={() => setVisibleCount((c) => c + LOAD_MORE_STEP)}>
                  加载更多{' '}
                  <span style={{ color: 'var(--ink-3)' }}>
                    · 已显示 {shown} / {totalMatches}
                  </span>
                </button>
              </div>
            </div>
          ) : null}
        </>
      )}
    </div>
  )
}
