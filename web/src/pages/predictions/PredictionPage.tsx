import { useEffect, useMemo, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import {
  getPrediction,
  type PredictionDetail,
  type PredictionMember,
  type PredictionTeam,
} from '../../lib/data'
import { formatDateTime, formatScoreInt } from '../../lib/format'
import {
  predictionMedalCounts,
  predictionRankingRows,
  type PredictionMedal,
  type PredictionRankingMethod,
} from './medals'
import './prediction.css'

function predictionSchedule(startAt: string | null): string {
  return startAt ? formatDateTime(startAt) : '时间待定'
}

type Method = PredictionRankingMethod

const MEDAL_LABEL: Record<PredictionMedal, string> = {
  gold: '金牌',
  silver: '银牌',
  bronze: '铜牌',
}

const MEDAL_TIER_ORDER = [
  ['final', '决赛'],
  ['regional', '区域赛'],
  ['invitational', '邀请赛'],
  ['provincial', '省赛'],
] as const

function PredictionMedalBadge({
  medal,
}: {
  medal: PredictionMedal | null
}) {
  if (!medal) return <span className="prediction-medal-empty">—</span>
  return (
    <span className={`prediction-medal prediction-medal--${medal}`}>
      <span aria-hidden="true" />
      {MEDAL_LABEL[medal]}
    </span>
  )
}

function HistoricalMedals({
  team,
  complete = false,
}: {
  team: PredictionTeam
  complete?: boolean
}) {
  const allRows = MEDAL_TIER_ORDER.map(([tier, label]) => ({
    tier,
    label,
    counts: team.historicalMedalsByTier?.[tier] ?? {
      gold: 0,
      silver: 0,
      bronze: 0,
    },
  }))
  const rows = complete
    ? allRows
    : allRows.filter(
        ({ counts }) => counts.gold || counts.silver || counts.bronze,
      )

  if (rows.length === 0)
    return <span className="prediction-medal-empty">—</span>

  return (
    <span className="prediction-medal-tally tnum">
      {rows.map(({ tier, label, counts }) => (
        <span className="prediction-medal-tally__row" key={tier}>
          <b>{label}</b>
          <span className="is-gold">金 {counts.gold}</span>
          <span className="is-silver">银 {counts.silver}</span>
          <span className="is-bronze">铜 {counts.bronze}</span>
        </span>
      ))}
    </span>
  )
}

function AwardCutoffTable({ prediction }: { prediction: PredictionDetail }) {
  const counts = predictionMedalCounts(prediction.officialTeamCount)
  const endpoints = [
    { medal: 'gold' as const, rank: counts.gold },
    { medal: 'silver' as const, rank: counts.gold + counts.silver },
    {
      medal: 'bronze' as const,
      rank: counts.gold + counts.silver + counts.bronze,
    },
  ]
  const officialTeams = prediction.teams.filter((team) => team.official)
  const ratingTeams = predictionRankingRows(
    officialTeams,
    'rating',
    prediction.officialTeamCount,
  ).map(({ team }) => team)
  const medalTeams = predictionRankingRows(
    officialTeams,
    'medals',
    prediction.officialTeamCount,
  ).map(({ team }) => team)

  return (
    <section className="wrap prediction-cutoff-section">
      <div className="section-label">
        <span className="eyebrow">预计奖牌线</span>
      </div>
      <div className="board-card prediction-cutoff-card">
        <table className="tbl prediction-cutoff-table">
          <thead>
            <tr>
              <th>排序方法</th>
              {endpoints.map(({ medal, rank }) => (
                <th className={`prediction-cutoff-heading prediction-cutoff-heading--${medal}`} key={medal}>
                  <span>
                    <i aria-hidden="true" />
                    {MEDAL_LABEL[medal]}
                  </span>
                  <small>截至第 {rank} 名</small>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            <tr>
              <th scope="row">积分排序</th>
              {endpoints.map(({ medal, rank }) => {
                const team = ratingTeams[rank - 1]
                return (
                  <td key={medal}>
                    <b className="prediction-cutoff-score tnum">
                      {team ? formatScoreInt(team.officialStrength) : '—'}
                    </b>
                  </td>
                )
              })}
            </tr>
            <tr>
              <th scope="row">奖牌排序</th>
              {endpoints.map(({ medal, rank }) => {
                const team = medalTeams[rank - 1]
                return (
                  <td key={medal}>
                    {team ? (
                      <HistoricalMedals team={team} complete />
                    ) : (
                      '—'
                    )}
                  </td>
                )
              })}
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  )
}

function MemberList({ members }: { members: PredictionMember[] }) {
  return (
    <span className="prediction-members">
      {members.map((member, index) => {
        const matched = member.matchedOfficial
        return (
          <span key={`${member.key}-${index}`}>
            {index > 0 ? (
              <span className="prediction-members__sep"> / </span>
            ) : null}
            {matched ? (
              <Link
                className="prediction-members__link"
                to={`/player/${encodeURIComponent(member.key)}`}
                title={`${member.officialRating} 分`}
              >
                {member.name}
              </Link>
            ) : (
              <span
                className="prediction-members__unmatched"
                title="无历史记录，按 1400 分计算"
              >
                {member.name}
              </span>
            )}
          </span>
        )
      })}
    </span>
  )
}

function TeamTable({
  prediction,
  method,
  query,
}: {
  prediction: PredictionDetail
  method: Method
  query: string
}) {
  const rows = useMemo(() => {
    const needle = query.trim().toLowerCase()
    return predictionRankingRows(
      prediction.teams.filter((team) => team.official),
      method,
      prediction.officialTeamCount,
    ).filter(({ team }) => {
      if (!needle) return true
      return [team.name, team.org, ...team.members.map((member) => member.name)]
        .join('\n')
        .toLowerCase()
        .includes(needle)
    })
  }, [method, prediction.officialTeamCount, prediction.teams, query])

  return (
    <div className="board-card prediction-table-card">
      <div className="table-scroll">
        <table className="tbl prediction-table">
          <thead>
            <tr>
              <th className="prediction-col-rank">预测</th>
              <th
                className="prediction-col-award"
                title="预计奖项仅由当前预测名次产生，不参与名次排序"
              >
                预计奖项
              </th>
              <th className="prediction-col-team">队伍</th>
              <th className="prediction-col-school">学校</th>
              <th className="prediction-col-members">队员</th>
              <th className="prediction-col-seat">座位</th>
              <th className="right prediction-col-score">
                {method === 'rating' ? '队伍强度' : '分级历史奖牌'}
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map(({ team, rank, medal }) => (
              <tr key={team.number}>
                <td className="prediction-col-rank"><span className="rank">{rank}</span></td>
                <td className="prediction-col-award">
                  <PredictionMedalBadge medal={medal} />
                </td>
                <td className="prediction-col-team">
                  <span className="prediction-team-name">
                    {team.name}
                  </span>
                  <small className="prediction-team-number tnum">
                    #{team.number}
                  </small>
                </td>
                <td className="muted prediction-col-school">{team.org}</td>
                <td className="prediction-col-members">
                  <MemberList members={team.members} />
                </td>
                <td className="dim tnum prediction-col-seat">{team.seat}</td>
                <td className="right score-strong prediction-col-score">
                  {method === 'rating' ? (
                    formatScoreInt(team.officialStrength)
                  ) : (
                    <HistoricalMedals team={team} />
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {rows.length === 0 ? (
        <div className="prediction-empty">没有符合搜索条件的队伍。</div>
      ) : null}
    </div>
  )
}

export default function PredictionPage() {
  const { slug = '' } = useParams()
  const [searchParams, setSearchParams] = useSearchParams()
  const method: Method =
    searchParams.get('method') === 'medals' ? 'medals' : 'rating'
  const [prediction, setPrediction] = useState<PredictionDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [query, setQuery] = useState('')

  useEffect(() => {
    let active = true
    getPrediction(slug)
      .then((data) => {
        if (active) setPrediction(data)
      })
      .catch((reason: unknown) => {
        if (active)
          setError(reason instanceof Error ? reason.message : '预测数据加载失败')
      })
    return () => {
      active = false
    }
  }, [slug])

  function selectMethod(next: Method) {
    setSearchParams((previous) => {
      const params = new URLSearchParams(previous)
      params.delete('board')
      if (next === 'rating') params.delete('method')
      else params.set('method', 'medals')
      return params
    })
  }

  if (error) {
    return (
      <div className="state" role="alert">
        <p className="state__title">无法加载预测</p>
        <p>{error}</p>
      </div>
    )
  }
  if (!prediction) return <div className="state" role="status">预测加载中…</div>

  return (
    <div className="page-enter prediction-page">
      <section className="wrap prediction-detail__head">
        <Link className="crumb" to="/predictions">← 返回赛前预测</Link>
        <span className="eyebrow eyebrow--oxford">RATING FORECAST · 2026</span>
        <h1 className="display">{prediction.shortTitle}</h1>
        <p className="prediction-detail__full-title">{prediction.title}</p>
        <div className="prediction-detail__meta">
          <span>{predictionSchedule(prediction.startAt)}</span>
          <span>{prediction.teamCount} 支队伍</span>
          <span>{prediction.officialTeamCount} 支正式队伍</span>
          <span>名单更新于 {prediction.sourceDate ?? '—'}</span>
        </div>
      </section>

      <AwardCutoffTable prediction={prediction} />

      <section className="band--2 prediction-ranking-section">
        <div className="wrap">
          <div className="prediction-ranking__top">
            <div>
              <span className="eyebrow">完整预测榜</span>
              <h2 className="serif">队伍预测名次</h2>
              <p className="prediction-ranking__basis">
                {method === 'rating'
                  ? '按赛前历史积分模型排序；预计奖项只表示该名次对应的获奖区间。'
                  : '先比较决赛奖牌，再依次比较区域赛、邀请赛和省赛；每一级内按金、银、铜比较。预计奖项不参与排序。'}
              </p>
            </div>
            <div className="caliber" aria-label="预测方式">
              <div className="caliber__set" role="tablist">
                <button
                  type="button"
                  className={`caliber__tab ${method === 'rating' ? 'is-active' : ''}`}
                  onClick={() => selectMethod('rating')}
                  role="tab"
                  aria-selected={method === 'rating'}
                >
                  积分排序
                </button>
                <button
                  type="button"
                  className={`caliber__tab ${method === 'medals' ? 'is-active' : ''}`}
                  onClick={() => selectMethod('medals')}
                  role="tab"
                  aria-selected={method === 'medals'}
                >
                  奖牌排序
                </button>
              </div>
            </div>
          </div>
          <div className="prediction-toolbar">
            <input
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="搜索队伍、学校或选手"
              aria-label="搜索预测队伍"
            />
          </div>
          <TeamTable prediction={prediction} method={method} query={query} />
        </div>
      </section>

      <section className="wrap prediction-method">
        <div>
          <span className="eyebrow">如何阅读</span>
          <h2 className="serif">这是历史数据预测，不是确定赛果</h2>
        </div>
        <ol>
          {prediction.notes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ol>
        <p>
          数据来源：{prediction.source}。
        </p>
      </section>
    </div>
  )
}
