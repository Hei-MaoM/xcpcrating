import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Caret } from '../../components/ui'
import { getLeaderboard, type LeaderboardRow } from '../../lib/data'
import { formatScoreInt } from '../../lib/format'
import { tiedRanks } from '../../lib/rank'
import { buildSchoolOptions } from './schools'
import { SchoolFilter } from './SchoolFilter'
import { useLeaderboardParams } from './useLeaderboardParams'

const PAGE_SIZE = 100
const RISE_ROWS = 14 // cascade-animate only the first screenful

/** A board row carrying its full-board rank (1224 ties on the rounded score). */
interface RankedRow extends LeaderboardRow {
  rank: number
}

/**
 * Assign full-board ranks. The board arrives ordered by full-precision rating
 * descending, so ranking on the rounded score gives players who share a rounded
 * score the same rank (1224 ties); the score itself is rounded only at display.
 */
function withRank(board: LeaderboardRow[]): RankedRow[] {
  const ranks = tiedRanks(board.map((row) => row.rating))
  return board.map((row, i) => ({ ...row, rank: ranks[i] }))
}

interface RatingsBoardProps {
  /** Official-only caliber (打星/非正式 excluded) vs the all-participation board. */
  official: boolean
}

/**
 * The current-rating leaderboard (正式参赛 / 全部参赛). Fetches the matching
 * board, applies the school filter, and paginates. Ranks are full-board positions
 * so a school filter shows each player's global standing, not a re-rank.
 */
export function RatingsBoard({ official }: RatingsBoardProps) {
  const navigate = useNavigate()
  const { page, org, setPage, setOrg } = useLeaderboardParams()

  const [rows, setRows] = useState<RankedRow[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  // Refetch when the caliber switches; null rows show the loading state meanwhile.
  useEffect(() => {
    let active = true
    setRows(null)
    setError(null)
    getLeaderboard(official)
      .then((data) => {
        if (active) setRows(withRank(data))
      })
      .catch((err: unknown) => {
        if (active) setError(err instanceof Error ? err.message : '榜单数据加载失败')
      })
    return () => {
      active = false
    }
  }, [official])

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
    <>
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
                          <span className="rank">{r.rank}</span>
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
                          <span className="score-strong">{formatScoreInt(r.rating)}</span>
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
    </>
  )
}
