import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Caret } from '../../components/ui'
import { dataUrl } from '../../lib/data'
import { formatScoreInt } from '../../lib/format'
import { SchoolFilter } from './SchoolFilter'
import { EndDatePicker } from './EndDatePicker'
import { useLeaderboardParams } from './useLeaderboardParams'
import { dateToInt } from './period'
import type { PeriodPageResult } from './periodWorkerCore'
import type {
  PeriodBounds,
  PeriodWorkerRequest,
  PeriodWorkerResponse,
} from './periodWorkerProtocol'

const PAGE_SIZE = 100

/** `YYYYMMDD` int → `YYYY-MM-DD` string. */
function intToDate(value: number): string {
  const s = String(value)
  return `${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6, 8)}`
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

  const workerRef = useRef<Worker | null>(null)
  const requestIdRef = useRef(0)
  const [bounds, setBounds] = useState<PeriodBounds | null>(null)
  const [result, setResult] = useState<PeriodPageResult | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const worker = new Worker(new URL('./period.worker.ts', import.meta.url), {
      type: 'module',
    })
    workerRef.current = worker
    worker.onmessage = (event: MessageEvent<PeriodWorkerResponse>) => {
      const message = event.data
      if (message.type === 'loaded') {
        setBounds(message.bounds)
      } else if (message.type === 'result') {
        if (message.id !== requestIdRef.current) return
        setResult(message)
        setLoading(false)
      } else if (message.id === undefined || message.id === requestIdRef.current) {
        setError(message.message)
        setLoading(false)
      }
    }
    worker.onerror = () => {
      setError('时间段数据加载失败')
      setLoading(false)
    }
    const request: PeriodWorkerRequest = {
      type: 'load',
      url: dataUrl('period-index.json'),
    }
    worker.postMessage(request)
    return () => {
      worker.terminate()
      workerRef.current = null
    }
  }, [])

  const minDate = bounds ? intToDate(bounds.lo) : ''
  const maxDate = bounds ? intToDate(bounds.hi) : ''
  const toStr = to ?? maxDate

  useEffect(() => {
    if (!bounds || !workerRef.current) return
    const id = requestIdRef.current + 1
    requestIdRef.current = id
    setLoading(true)
    setError(null)
    const request: PeriodWorkerRequest = {
      type: 'query',
      id,
      toInt: dateToInt(toStr) ?? bounds.hi,
      org,
      page,
      pageSize: PAGE_SIZE,
    }
    workerRef.current.postMessage(request)
  }, [bounds, toStr, org, page])

  const schoolOptions = result?.schoolOptions ?? []
  const total = result?.total ?? 0
  const totalPages = result?.pageCount ?? 1
  const clampedPage = result?.page ?? page
  const start = (clampedPage - 1) * PAGE_SIZE
  const pageRows = result?.rows ?? []

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
          disabled={bounds === null}
        />
        <span className="toolbar__count">
          截至该日 <span className="tnum">{(result?.overallTotal ?? 0).toLocaleString('en-US')}</span> 名正式参赛选手
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
      ) : result === null ? (
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
                  {pageRows.map((r) => {
                    return (
                      <tr
                        key={r.key}
                        className="row-link"
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
                  disabled={loading || clampedPage <= 1}
                  aria-label="上一页"
                  onClick={() => setPage(clampedPage - 1)}
                >
                  <Caret dir="left" />
                </button>
                <button
                  className="pager__btn"
                  disabled={loading || clampedPage >= totalPages}
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
