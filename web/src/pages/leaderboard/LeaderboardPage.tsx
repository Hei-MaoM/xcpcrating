import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Caret } from '../../components/ui'
import { getLeaderboard, type LeaderboardRow } from '../../lib/data'
import { formatScore } from '../../lib/format'
import { buildSchoolOptions } from './schools'
import { SchoolFilter } from './SchoolFilter'
import { useLeaderboardParams } from './useLeaderboardParams'

const PAGE_SIZE = 100
const RISE_ROWS = 14 // cascade-animate only the first screenful

/** A board row carrying its stable 1-based overall rank (full-board position). */
interface RankedRow extends LeaderboardRow {
  rank: number
}

function withRank(board: LeaderboardRow[]): RankedRow[] {
  return board.map((row, i) => ({ ...row, rank: i + 1 }))
}

type BoardKind = 'all' | 'official'

export default function LeaderboardPage() {
  const navigate = useNavigate()
  const { page, org, setPage, setOrg } = useLeaderboardParams()
  const [searchParams, setSearchParams] = useSearchParams()
  // Default caliber: 正式参赛. ?board=all selects the all-participation board.
  const board: BoardKind = searchParams.get('board') === 'all' ? 'all' : 'official'

  const [rows, setRows] = useState<RankedRow[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  // Refetch when the board switches; null rows show the loading state meanwhile.
  useEffect(() => {
    let active = true
    setRows(null)
    setError(null)
    getLeaderboard(board === 'official')
      .then((data) => {
        if (active) setRows(withRank(data))
      })
      .catch((err: unknown) => {
        if (active) setError(err instanceof Error ? err.message : '榜单数据加载失败')
      })
    return () => {
      active = false
    }
  }, [board])

  // Switch board: persist in the URL and reset to the first page.
  function selectBoard(next: BoardKind) {
    setSearchParams(
      (prev) => {
        const merged = new URLSearchParams(prev)
        if (next === 'all') merged.set('board', 'all')
        else merged.delete('board')
        merged.delete('page')
        return merged
      },
      { replace: false },
    )
  }

  const schoolOptions = useMemo(() => buildSchoolOptions(rows ?? []), [rows])

  const filtered = useMemo<RankedRow[]>(() => {
    if (!rows) return []
    if (!org) return rows
    return rows.filter((r) => r.org === org)
  }, [rows, org])

  const total = filtered.length
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const clampedPage = Math.min(Math.max(1, page), totalPages)
  const start = (clampedPage - 1) * PAGE_SIZE
  const pageRows = filtered.slice(start, start + PAGE_SIZE)

  return (
    <div className="page-enter">
      <section className="wrap phead">
        <span className="eyebrow eyebrow--oxford">积分榜单</span>
        <h1 className="display">选手榜单</h1>
      </section>

      <section className="wrap" style={{ paddingBottom: 64 }}>
        <div className="board-tabs">
          <div className="board-tabs__set" role="tablist" aria-label="榜单类型">
            <button
              type="button"
              role="tab"
              aria-selected={board === 'official'}
              className={`board-tab ${board === 'official' ? 'is-active' : ''}`}
              onClick={() => selectBoard('official')}
            >
              正式参赛
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={board === 'all'}
              className={`board-tab ${board === 'all' ? 'is-active' : ''}`}
              onClick={() => selectBoard('all')}
            >
              全部参赛
            </button>
          </div>
          <span className="board-tabs__hint">
            {board === 'official'
              ? '仅计入正式参赛，打星（非正式）场次不计。'
              : '全部成绩计入积分，含打星（非正式）场次。'}
          </span>
        </div>

        <div className="toolbar">
          <SchoolFilter
            value={org}
            options={schoolOptions}
            onChange={(next) => {
              setOrg(next)
            }}
            disabled={rows === null}
          />
          <span className="toolbar__count">
            共 <span className="tnum">{(rows?.length ?? 0).toLocaleString('en-US')}</span> 名选手
            {org ? (
              <>
                {' '}· 当前 {org} <span className="tnum">{total}</span> 人
              </>
            ) : null}
          </span>
        </div>

        {error ? (
          <div className="state" role="alert">
            <p className="state__title">无法加载榜单</p>
            <p>{error}</p>
          </div>
        ) : rows === null ? (
          <div className="state" role="status">
            榜单加载中…
          </div>
        ) : (
          <>
            <div className="board-card">
              <div className="table-scroll">
              <table className="tbl board-tbl">
                <colgroup>
                  <col style={{ width: '92px' }} />
                  <col />
                  <col style={{ width: '26%' }} />
                  <col style={{ width: '150px' }} />
                  <col style={{ width: '110px' }} />
                </colgroup>
                <thead>
                  <tr>
                    <th>名次</th>
                    <th>选手</th>
                    <th>学校</th>
                    <th className="right">分数</th>
                    <th className="right">场次</th>
                  </tr>
                </thead>
                <tbody>
                  {pageRows.map((r, i) => {
                    const rise = clampedPage === 1 && i < RISE_ROWS
                    return (
                      <tr
                        key={r.key}
                        className={`row-link ${rise ? 'row-rise' : ''}`}
                        style={rise ? { animationDelay: `${i * 45}ms` } : undefined}
                        tabIndex={0}
                        onClick={() => navigate(`/player/${encodeURIComponent(r.key)}`)}
                        onKeyDown={(e) =>
                          e.key === 'Enter' &&
                          navigate(`/player/${encodeURIComponent(r.key)}`)
                        }
                      >
                        <td>
                          {r.rank <= 3 ? (
                            <span className={`medal-rank medal-rank--${r.rank}`}>{r.rank}</span>
                          ) : (
                            <span className="rank">{r.rank}</span>
                          )}
                        </td>
                        <td>
                          <span className="player-name">{r.name}</span>
                        </td>
                        <td>
                          <span
                            className="school-link"
                            role="button"
                            tabIndex={-1}
                            onClick={(e) => {
                              e.stopPropagation()
                              setOrg(r.org)
                            }}
                          >
                            {r.org || '—'}
                          </span>
                        </td>
                        <td className="right">
                          <span className="score-strong">{formatScore(r.rating)}</span>
                        </td>
                        <td className="right muted">{r.contests}</td>
                      </tr>
                    )
                  })}
                  {pageRows.length === 0 ? (
                    <tr>
                      <td colSpan={5} className="center dim" style={{ height: 120 }}>
                        {org ? `${org} 暂无上榜选手。` : '暂无上榜选手。'}
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
