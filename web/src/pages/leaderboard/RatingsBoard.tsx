import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Caret } from '../../components/ui'
import {
  getLeaderboardMeta,
  getLeaderboardPage,
  getLeaderboardSchool,
  type LeaderboardMeta,
  type LeaderboardRow,
} from '../../lib/data'
import { formatScoreInt } from '../../lib/format'
import { SchoolFilter } from './SchoolFilter'
import type { SchoolOption } from './schools'
import { useLeaderboardParams } from './useLeaderboardParams'

const PAGE_SIZE = 100

interface RatingsBoardProps {
  /** Official-only caliber (打星/非正式 excluded) vs the all-participation board. */
  official: boolean
}

interface MetaLoadState {
  official: boolean
  data?: LeaderboardMeta
  error?: string
}

interface RowsLoadState {
  key: string
  data?: LeaderboardRow[]
  error?: string
}

/**
 * The current-rating leaderboard. Metadata carries total/school counts; the
 * browser fetches only the current 100-row page or one small school hash bucket.
 * Every row already carries its global rank from the exporter.
 */
export function RatingsBoard({ official }: RatingsBoardProps) {
  const navigate = useNavigate()
  const { page, org, setPage, setOrg } = useLeaderboardParams()

  const [metaLoad, setMetaLoad] = useState<MetaLoadState | null>(null)
  const [rowsLoad, setRowsLoad] = useState<RowsLoadState | null>(null)
  const meta = metaLoad?.official === official ? (metaLoad.data ?? null) : null
  const metaError =
    metaLoad?.official === official ? (metaLoad.error ?? null) : null

  useEffect(() => {
    let active = true
    getLeaderboardMeta(official)
      .then((data) => {
        if (active) setMetaLoad({ official, data })
      })
      .catch((err: unknown) => {
        if (active)
          setMetaLoad({
            official,
            error: err instanceof Error ? err.message : '榜单数据加载失败',
          })
      })
    return () => {
      active = false
    }
  }, [official])

  const schoolOptions = useMemo<SchoolOption[]>(
    () =>
      (meta?.schools ?? [])
        .map(([school, count]) => ({ org: school, count }))
        .sort(
          (a, b) =>
            b.count - a.count || a.org.localeCompare(b.org, 'zh-CN'),
        ),
    [meta],
  )
  const schoolCount = org
    ? (meta?.schools.find(([school]) => school === org)?.[1] ?? 0)
    : null
  const total = org ? schoolCount ?? 0 : (meta?.total ?? 0)
  const pageSize = meta?.pageSize ?? PAGE_SIZE
  const totalPages = Math.max(1, Math.ceil(total / pageSize))
  const clampedPage = Math.min(Math.max(1, page), totalPages)
  const start = (clampedPage - 1) * pageSize
  const invalidSchool = Boolean(org && meta && schoolCount === 0)
  const loadKey = JSON.stringify([official, org, clampedPage, pageSize])
  const rows = invalidSchool
    ? []
    : rowsLoad?.key === loadKey
      ? (rowsLoad.data ?? null)
      : null
  const rowsError = rowsLoad?.key === loadKey ? (rowsLoad.error ?? null) : null
  const error = metaError ?? rowsError
  const pageRows = rows ?? []

  useEffect(() => {
    if (!meta || invalidSchool) return
    let active = true
    const load = org
      ? getLeaderboardSchool(official, org).then((schoolRows) =>
          schoolRows.slice(start, start + pageSize),
        )
      : getLeaderboardPage(official, clampedPage)
    load
      .then((data) => {
        if (active) setRowsLoad({ key: loadKey, data })
      })
      .catch((err: unknown) => {
        if (active)
          setRowsLoad({
            key: loadKey,
            error: err instanceof Error ? err.message : '榜单数据加载失败',
          })
      })
    return () => {
      active = false
    }
  }, [meta, official, org, invalidSchool, start, pageSize, clampedPage, loadKey])

  return (
    <>
      <div className="toolbar">
        <SchoolFilter
          value={org}
          options={schoolOptions}
          onChange={(next) => {
            setOrg(next)
          }}
          disabled={meta === null}
        />
        <span className="toolbar__count">
          共 <span className="tnum">{(meta?.total ?? 0).toLocaleString('en-US')}</span> 名选手
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
      ) : meta === null || rows === null ? (
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
