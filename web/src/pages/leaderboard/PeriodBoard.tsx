import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Caret } from '../../components/ui'
import { getPeriodIndex, type PeriodRow } from '../../lib/data'
import { formatScoreInt } from '../../lib/format'
import { buildSchoolOptions } from './schools'
import { SchoolFilter } from './SchoolFilter'
import { EndDatePicker } from './EndDatePicker'
import { useLeaderboardParams } from './useLeaderboardParams'
import { buildPeriodBoard, dateToInt, type PeriodBoardRow } from './period'

const PAGE_SIZE = 100
const RISE_ROWS = 14

/** `YYYYMMDD` int → `YYYY-MM-DD` string. */
function intToDate(value: number): string {
  const s = String(value)
  return `${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6, 8)}`
}

/** Earliest / latest official-participation date present in the timelines. */
function dataBounds(rows: PeriodRow[]): { lo: number; hi: number } | null {
  let lo = Infinity
  let hi = -Infinity
  for (const [, , , dates] of rows) {
    if (dates.length === 0) continue
    if (dates[0] < lo) lo = dates[0]
    if (dates[dates.length - 1] > hi) hi = dates[dates.length - 1]
  }
  return Number.isFinite(lo) ? { lo, hi } : null
}

/**
 * The 时间段 board: pick an end date and see the official board *as of that
 * date* — every player who had an official participation on-or-before it, scored
 * by their official rating at that point (历史快照, not their current rating),
 * with their cumulative official participation count. The end date defaults to
 * the latest data date and lives in the URL (`?to`) so a view is shareable.
 * Ranks are board-global, matching the ratings board under a school filter.
 */
export function PeriodBoard() {
  const navigate = useNavigate()
  const { page, org, to, setPage, setOrg, setTo } = useLeaderboardParams()

  const [rows, setRows] = useState<PeriodRow[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    getPeriodIndex()
      .then((data) => {
        if (active) setRows(data)
      })
      .catch((err: unknown) => {
        if (active)
          setError(err instanceof Error ? err.message : '时间段数据加载失败')
      })
    return () => {
      active = false
    }
  }, [])

  const bounds = useMemo(() => (rows ? dataBounds(rows) : null), [rows])
  const minDate = bounds ? intToDate(bounds.lo) : ''
  const maxDate = bounds ? intToDate(bounds.hi) : ''

  // Effective end date: URL value when present (and in range), else the latest.
  const toStr = to ?? maxDate

  // Open-ended board: from = 0 means "everyone on-or-before `to`" (cumulative).
  const fullBoard = useMemo<PeriodBoardRow[]>(() => {
    if (!rows || !bounds) return []
    const toInt = dateToInt(toStr) ?? bounds.hi
    return buildPeriodBoard(rows, 0, toInt)
  }, [rows, bounds, toStr])

  const schoolOptions = useMemo(() => buildSchoolOptions(fullBoard), [fullBoard])

  const filtered = useMemo<PeriodBoardRow[]>(
    () => (org ? fullBoard.filter((r) => r.org === org) : fullBoard),
    [fullBoard, org],
  )

  const total = filtered.length
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const clampedPage = Math.min(Math.max(1, page), totalPages)
  const start = (clampedPage - 1) * PAGE_SIZE
  const pageRows = filtered.slice(start, start + PAGE_SIZE)

  const atLatest = !to || to === maxDate

  return (
    <>
      <div className="period-range">
        {bounds ? (
          <EndDatePicker
            value={toStr}
            min={minDate}
            max={maxDate}
            onChange={(next) => setTo(next === maxDate ? null : next)}
          />
        ) : (
          <span className="datepick__trigger" aria-disabled="true">
            <span className="datepick__tag">截至</span>
            <span className="datepick__value">加载中…</span>
          </span>
        )}
        {!atLatest ? (
          <button
            type="button"
            className="period-range__reset"
            onClick={() => setTo(null)}
          >
            至今
          </button>
        ) : null}
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
          截至该日 <span className="tnum">{fullBoard.length.toLocaleString('en-US')}</span> 名正式参赛选手
          {org ? (
            <>
              {' '}· 当前 {org} <span className="tnum">{total}</span> 人
            </>
          ) : null}
        </span>
      </div>

      {error ? (
        <div className="state" role="alert">
          <p className="state__title">无法加载时间段榜单</p>
          <p>{error}</p>
        </div>
      ) : rows === null ? (
        <div className="state" role="status">
          时间段数据加载中…
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
                    <th className="right">期末分数</th>
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
                        <td className="right muted">{r.count}</td>
                      </tr>
                    )
                  })}
                  {pageRows.length === 0 ? (
                    <tr>
                      <td colSpan={5} className="center dim" style={{ height: 120 }}>
                        {org
                          ? `${org} 截至该日暂无正式参赛选手。`
                          : '截至该日暂无正式参赛选手。'}
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
