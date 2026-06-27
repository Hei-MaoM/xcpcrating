import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Caret, SearchIcon } from '../../components/ui'
import { getSchools, type SchoolRow } from '../../lib/data'
import { formatScoreInt } from '../../lib/format'
import { tiedRanks } from '../../lib/rank'
import { useDebounce } from '../../lib/useDebounce'

const PAGE_SIZE = 100
const RISE_ROWS = 14 // cascade-animate only the first screenful

/** A school row carrying its full-board rank (1224 ties on the rounded score). */
interface RankedSchool extends SchoolRow {
  rank: number
}

/**
 * Assign full-board ranks. schools.json arrives ordered by full-precision rating
 * descending, so ranking on the rounded score gives schools sharing a rounded
 * score the same rank (1224 ties); the score itself is rounded only at display.
 */
function withRank(board: SchoolRow[]): RankedSchool[] {
  const ranks = tiedRanks(board.map((row) => row.rating))
  return board.map((row, i) => ({ ...row, rank: ranks[i] }))
}

/**
 * 学校榜: the school ranking from the TrueSkill-family school rating engine.
 * Ranks are full-board positions (so a name search shows a school's real
 * standing, not a re-rank); clicking a school opens the player board filtered to
 * that school. A debounced name search narrows the ~1.4k schools client-side.
 */
export default function SchoolsPage() {
  const navigate = useNavigate()

  const [rows, setRows] = useState<RankedSchool[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [page, setPage] = useState(1)
  const term = useDebounce(query.trim(), 180)

  useEffect(() => {
    let active = true
    getSchools()
      .then((data) => {
        if (active) setRows(withRank(data))
      })
      .catch((err: unknown) => {
        if (active) setError(err instanceof Error ? err.message : '学校榜数据加载失败')
      })
    return () => {
      active = false
    }
  }, [])

  const filtered = useMemo<RankedSchool[]>(() => {
    if (!rows) return []
    if (!term) return rows
    const needle = term.toLowerCase()
    return rows.filter((r) => r.org.toLowerCase().includes(needle))
  }, [rows, term])

  const total = filtered.length
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const clampedPage = Math.min(Math.max(1, page), totalPages)
  const start = (clampedPage - 1) * PAGE_SIZE
  const pageRows = filtered.slice(start, start + PAGE_SIZE)

  return (
    <div className="page-enter">
      <section className="wrap phead">
        <span className="eyebrow eyebrow--oxford">院校排名</span>
        <h1 className="display">学校榜</h1>
      </section>

      <section className="wrap" style={{ paddingBottom: 64 }}>
        <div className="board-tabs">
          <div className="board-tabs__set" role="tablist" aria-label="榜单类型">
            <span className="board-tab is-active" role="tab" aria-selected="true">
              学校
            </span>
          </div>
          <span className="board-tabs__hint">
            每场按各校最强正式队伍的名次排名；表现分经贝叶斯零和更新（全场涨跌相抵、对单场极端值稳健）。
          </span>
        </div>

        <div className="toolbar">
          <div className="school-search">
            <SearchIcon size={15} />
            <input
              value={query}
              onChange={(e) => {
                setQuery(e.target.value)
                setPage(1) // a new query re-shapes the result set → first page
              }}
              placeholder="搜索学校…"
              aria-label="搜索学校"
              disabled={rows === null}
            />
          </div>
          <span className="toolbar__count">
            共 <span className="tnum">{(rows?.length ?? 0).toLocaleString('en-US')}</span> 所学校
            {term ? (
              <>
                {' '}· 匹配 <span className="tnum">{total}</span> 所
              </>
            ) : null}
          </span>
        </div>

        {error ? (
          <div className="state" role="alert">
            <p className="state__title">无法加载学校榜</p>
            <p>{error}</p>
          </div>
        ) : rows === null ? (
          <div className="state" role="status">
            学校榜加载中…
          </div>
        ) : (
          <>
            <div className="board-card">
              <div className="table-scroll">
                <table className="tbl board-tbl">
                  <colgroup>
                    <col style={{ width: '92px' }} />
                    <col />
                    <col style={{ width: '150px' }} />
                    <col style={{ width: '110px' }} />
                  </colgroup>
                  <thead>
                    <tr>
                      <th>名次</th>
                      <th>学校</th>
                      <th className="right">评分</th>
                      <th className="right">场次</th>
                    </tr>
                  </thead>
                  <tbody>
                    {pageRows.map((r, i) => {
                      const rise = clampedPage === 1 && i < RISE_ROWS
                      const goto = () =>
                        navigate(`/school/${encodeURIComponent(r.org)}`)
                      return (
                        <tr
                          key={r.org}
                          className={`row-link ${rise ? 'row-rise' : ''}`}
                          style={rise ? { animationDelay: `${i * 45}ms` } : undefined}
                          tabIndex={0}
                          onClick={goto}
                          onKeyDown={(e) => e.key === 'Enter' && goto()}
                        >
                          <td>
                            <span className="rank">{r.rank}</span>
                          </td>
                          <td>
                            <span className="player-name">{r.org || '—'}</span>
                          </td>
                          <td className="right">
                            <span className="score-strong">{formatScoreInt(r.rating)}</span>
                          </td>
                          <td className="right muted">{r.contests}</td>
                        </tr>
                      )
                    })}
                    {pageRows.length === 0 ? (
                      <tr>
                        <td colSpan={4} className="center dim" style={{ height: 120 }}>
                          {term ? `无匹配学校。` : '暂无上榜学校。'}
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
