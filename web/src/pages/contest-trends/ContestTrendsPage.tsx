import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { ContestSectionNav } from '../contests/ContestSectionNav'
import {
  getContestsIndex,
  type ContestIndexEntry,
  type ContestStrengthScores,
} from '../../lib/data'
import { formatDate } from '../../lib/format'
import {
  CONTEST_TREND_KIND_LABELS,
  STRENGTH_COLUMNS,
  buildContestTrendSeasons,
  contestStrength,
  type ContestTrendKind,
  type ContestTrendRow,
} from './trend'
import './contest-trends.css'

function formatStrength(value: number | null): string {
  return value === null ? '—' : value.toFixed(2)
}

function formatCount(value: number | null): string {
  return value === null ? '—' : String(Math.round(value))
}

function KindBadge({ kind }: { kind: ContestTrendKind }) {
  const tone = kind.startsWith('icpc') ? 'icpc' : 'ccpc'
  const tier = kind.endsWith('regional') ? 'regional' : 'invitational'
  return (
    <span className={`badge badge--${tone} ct-kind ct-kind--${tier}`}>
      {CONTEST_TREND_KIND_LABELS[kind]}
    </span>
  )
}

function StrengthCell({
  row,
  metric,
}: {
  row: ContestTrendRow
  metric: keyof ContestStrengthScores
}) {
  const value = contestStrength(row.contest, metric)
  return (
    <td className={`right ct-score${value === null ? ' ct-score--missing' : ''}`}>
      {formatStrength(value)}
    </td>
  )
}

function ContestSeasonTable({
  season,
  rows,
}: {
  season: string
  rows: ContestTrendRow[]
}) {
  const headingId = `contest-trends-${season.replace('–', '-')}`
  return (
    <section className="ct-season" aria-labelledby={headingId}>
      <header className="ct-season__head">
        <div>
          <span className="ct-season__index tnum">{season}</span>
          <h2 id={headingId}>{season} 竞赛年逐场分数</h2>
        </div>
        <span className="ct-season__count tnum">{rows.length} 场</span>
      </header>

      <div className="board-card ct-table-card">
        <div className="table-scroll ct-table-scroll">
          <table className="tbl ct-table">
            <caption className="ct-sr-only">
              {season} 竞赛年 ICPC、CCPC 区域赛与邀请赛逐场赛前阵容分
            </caption>
            <thead>
              <tr>
                <th>日期</th>
                <th>类别</th>
                <th>比赛</th>
                {STRENGTH_COLUMNS.map(({ key, label }) => (
                  <th className="right" key={key}>
                    {label}
                  </th>
                ))}
                <th className="right" title="参加本场比赛的正式队伍">
                  正式队伍
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.contest.slug}>
                  <td className="ct-date tnum">
                    <time dateTime={row.contest.startAt}>
                      {formatDate(row.contest.startAt)}
                    </time>
                  </td>
                  <td>
                    <KindBadge kind={row.kind} />
                  </td>
                  <td className="ct-contest">
                    <Link to={`/contest/${row.contest.slug}`}>
                      {row.contest.title}
                    </Link>
                  </td>
                  {STRENGTH_COLUMNS.map(({ key }) => (
                    <StrengthCell key={key} row={row} metric={key} />
                  ))}
                  <td className="right ct-count">
                    {formatCount(
                      row.contest.contestMetrics?.effectiveTeamCount ?? null,
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  )
}

export default function ContestTrendsPage() {
  const [contests, setContests] = useState<ContestIndexEntry[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    getContestsIndex()
      .then((data) => {
        if (!cancelled) setContests(data)
      })
      .catch((reason: unknown) => {
        if (!cancelled) {
          setError(reason instanceof Error ? reason.message : '加载失败')
        }
      })
    return () => {
      cancelled = true
    }
  }, [])

  const seasons = useMemo(
    () => (contests ? buildContestTrendSeasons(contests) : []),
    [contests],
  )
  const contestCount = useMemo(
    () => seasons.reduce((total, season) => total + season.rows.length, 0),
    [seasons],
  )

  return (
    <div className="page-enter ct-page">
      <section className="wrap phead ct-head">
        <span className="eyebrow eyebrow--oxford">Season contest dossier</span>
        <h1 className="display">赛季比较</h1>
        <ContestSectionNav />
      </section>

      <section className="wrap ct-scope" aria-label="收录类别">
        <div className="ct-scope__kinds" aria-label="收录类别">
          {(Object.keys(CONTEST_TREND_KIND_LABELS) as ContestTrendKind[]).map(
            (kind) => <KindBadge key={kind} kind={kind} />,
          )}
        </div>
      </section>

      {error ? (
        <div className="state" role="alert">
          <p className="state__title">趋势数据加载失败</p>
          <p>{error}</p>
        </div>
      ) : contests === null ? (
        <div className="state" role="status">
          正在整理逐场分数…
        </div>
      ) : seasons.length === 0 ? (
        <div className="state" role="status">
          <p className="state__title">暂无可展示的比赛</p>
          <p>当前数据中没有带类别信息的 ICPC、CCPC 区域赛或邀请赛。</p>
        </div>
      ) : (
        <section className="wrap ct-seasons" aria-label="逐竞赛年原始记录">
          <div className="ct-seasons__summary">
            <h2>逐竞赛年原始记录</h2>
            <span className="tnum">
              {seasons.length} 个竞赛年 · {contestCount} 场比赛
            </span>
          </div>
          {seasons.map(({ season, rows }) => (
            <ContestSeasonTable key={season} season={season} rows={rows} />
          ))}
        </section>
      )}
    </div>
  )
}
