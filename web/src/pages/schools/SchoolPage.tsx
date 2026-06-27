import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Caret } from '../../components/ui'
import {
  getSchoolHistory,
  getSchools,
  type SchoolResultRow,
  type SchoolRow,
} from '../../lib/data'
import { formatDate, formatScoreDelta, formatScoreInt } from '../../lib/format'
import { tiedRanks } from '../../lib/rank'

/** Signed per-contest rating change, styled like the contest page's μ delta
 * (▲ rise red / ▼ fall green — the board's 红涨绿跌 convention). */
function DeltaCell({ delta }: { delta: number }) {
  const dir = delta > 0 ? 'rise' : delta < 0 ? 'fall' : 'flat'
  return (
    <span className={`mu-delta mu-delta--${dir}`}>
      <span aria-hidden="true">{dir === 'rise' ? '▲' : dir === 'fall' ? '▼' : '–'}</span>
      <span>{formatScoreDelta(delta)}</span>
    </span>
  )
}

const PAGE_SIZE = 50
const RISE_ROWS = 14

/** One labelled metric in the school header strip. */
function Metric({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="school-stat">
      <span className="school-stat__label">{label}</span>
      <span className="school-stat__value tnum">{value}</span>
    </div>
  )
}

/**
 * School detail page (route `/school/:org`): the school's 学校榜 standing plus its
 * 学校成绩 — every contest it competed in, with its best team's placement, its rank
 * among schools, and the performance that drove its rating that contest (newest
 * first). schools.json supplies the header; school-history the rows.
 */
export default function SchoolPage() {
  const params = useParams()
  const org = decodeURIComponent(params.org ?? '')
  // Key by org so navigating between schools remounts with fresh state.
  return <SchoolPageView key={org} org={org} />
}

function SchoolPageView({ org }: { org: string }) {
  const navigate = useNavigate()

  const [schools, setSchools] = useState<SchoolRow[] | null>(null)
  const [history, setHistory] = useState<SchoolResultRow[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [page, setPage] = useState(1)

  useEffect(() => {
    let active = true
    Promise.all([getSchools(), getSchoolHistory(org)])
      .then(([s, h]) => {
        if (!active) return
        setSchools(s)
        setHistory(h)
      })
      .catch((err: unknown) => {
        if (active) setError(err instanceof Error ? err.message : '学校数据加载失败')
      })
    return () => {
      active = false
    }
  }, [org])

  // The school's own standing (rank via 1224 ties over the rating-sorted board).
  const school = useMemo(() => {
    if (!schools) return null
    const ranks = tiedRanks(schools.map((s) => s.rating))
    const idx = schools.findIndex((s) => s.org === org)
    return idx < 0 ? null : { row: schools[idx], rank: ranks[idx] }
  }, [schools, org])

  // Best-ever 校排 (school standing among schools) across the school's history.
  const bestSchoolRank = useMemo(() => {
    if (!history || history.length === 0) return null
    return history.reduce((best, r) => Math.min(best, r.schoolRank), Infinity)
  }, [history])

  const loading = schools === null || history === null
  const total = history?.length ?? 0
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const clampedPage = Math.min(Math.max(1, page), totalPages)
  const start = (clampedPage - 1) * PAGE_SIZE
  const pageRows = history ? history.slice(start, start + PAGE_SIZE) : []

  return (
    <div className="page-enter">
      <section className="wrap phead">
        <span className="eyebrow eyebrow--oxford">学校</span>
        <h1 className="display">{org || '—'}</h1>
        {!loading && !error ? (
          <div className="school-stats">
            <Metric
              label="学校榜名次"
              value={school ? `第 ${school.rank}` : '—'}
            />
            <Metric
              label="评分"
              value={school ? formatScoreInt(school.row.rating) : '—'}
            />
            <Metric label="参赛场次" value={school ? school.row.contests : total} />
            <Metric
              label="最佳校排"
              value={bestSchoolRank === null ? '—' : `第 ${bestSchoolRank}`}
            />
          </div>
        ) : null}
      </section>

      <section className="wrap" style={{ paddingBottom: 64 }}>
        {error ? (
          <div className="state" role="alert">
            <p className="state__title">无法加载学校</p>
            <p>{error}</p>
          </div>
        ) : loading ? (
          <div className="state" role="status">
            加载中…
          </div>
        ) : (
          <>
            <div className="board-tabs">
              <div className="board-tabs__set" role="tablist" aria-label="榜单类型">
                <span className="board-tab is-active" role="tab" aria-selected="true">
                  学校成绩
                </span>
              </div>
              <span className="board-tabs__hint">
                逐场战绩：该校最强正式队伍的名次、校排，及驱动评分的表现分。
              </span>
            </div>

            <div className="board-card">
              <div className="table-scroll">
                <table className="tbl board-tbl">
                  <colgroup>
                    <col />
                    <col style={{ width: '128px' }} />
                    <col style={{ width: '140px' }} />
                    <col style={{ width: '104px' }} />
                    <col style={{ width: '104px' }} />
                  </colgroup>
                  <thead>
                    <tr>
                      <th>比赛</th>
                      <th>日期</th>
                      <th className="right">校排（最强队）</th>
                      <th className="right">表现分</th>
                      <th className="right">变化</th>
                    </tr>
                  </thead>
                  <tbody>
                    {pageRows.map((r, i) => {
                      const rise = clampedPage === 1 && i < RISE_ROWS
                      const goto = () => navigate(`/contest/${r.slug}`)
                      return (
                        <tr
                          key={`${r.slug}-${i}`}
                          className={`row-link ${rise ? 'row-rise' : ''}`}
                          style={rise ? { animationDelay: `${i * 45}ms` } : undefined}
                          tabIndex={0}
                          onClick={goto}
                          onKeyDown={(e) => e.key === 'Enter' && goto()}
                        >
                          <td>
                            <span className="player-name">{r.title}</span>
                          </td>
                          <td className="muted">{formatDate(r.startAt)}</td>
                          <td className="right tnum">
                            {r.schoolRank}
                            <span className="dim"> / {r.schoolCount}</span>
                          </td>
                          <td className="right">
                            <span className="score-strong">{formatScoreInt(r.perf)}</span>
                          </td>
                          <td className="right">
                            <DeltaCell delta={r.delta} />
                          </td>
                        </tr>
                      )
                    })}
                    {pageRows.length === 0 ? (
                      <tr>
                        <td colSpan={5} className="center dim" style={{ height: 120 }}>
                          暂无成绩记录。
                        </td>
                      </tr>
                    ) : null}
                  </tbody>
                </table>
              </div>
            </div>

            {total > 0 ? (
              <div className="pager">
                <span>
                  第 <span className="tnum">{start + 1}–{start + pageRows.length}</span> 项，共{' '}
                  <span className="tnum">{total.toLocaleString('en-US')}</span> 项
                </span>
                <div className="pager__ctrl">
                  <button
                    className="pager__btn"
                    disabled={clampedPage <= 1}
                    aria-label="上一页"
                    onClick={() => setPage(clampedPage - 1)}
                  >
                    <Caret dir="left" />
                  </button>
                  <button
                    className="pager__btn"
                    disabled={clampedPage >= totalPages}
                    aria-label="下一页"
                    onClick={() => setPage(clampedPage + 1)}
                  >
                    <Caret dir="right" />
                  </button>
                </div>
              </div>
            ) : null}
          </>
        )}
      </section>
    </div>
  )
}
