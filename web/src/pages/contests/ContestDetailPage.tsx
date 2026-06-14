import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { getContest, type ContestDetail, type ContestTeam } from '../../lib/data'
import { formatDate, formatPenalty, formatScore } from '../../lib/format'
import { Caret, Delta, Deviation } from '../../components/ui'
import { categoryLabel } from './categories'

type ContestTab = 'results' | 'prediction'

const ROWS_PER_PAGE = 100

function isContestTab(value: string | null): value is ContestTab {
  return value === 'results' || value === 'prediction'
}

/** Category badge mapped to the Light Luxury palette. */
function CatBadge({ category }: { category: string }) {
  const cls = category === 'icpc' ? 'icpc' : category === 'ccpc' ? 'ccpc' : 'prov'
  return <span className={`badge badge--${cls}`}>{categoryLabel(category)}</span>
}

function MemberList({ members }: { members: ContestTeam['members'] }) {
  return (
    <span className="dim members">
      {members.map((m, i) => (
        <span key={m.key}>
          <Link
            to={`/player/${encodeURIComponent(m.key)}`}
            onClick={(e) => e.stopPropagation()}
            style={{ color: 'inherit' }}
          >
            {m.name}
          </Link>
          {i < members.length - 1 ? '、' : ''}
        </span>
      ))}
    </span>
  )
}

function RankCell({ rank }: { rank: number }) {
  return <span className="rank">{rank}</span>
}

function ResultsTable({ teams }: { teams: ContestTeam[] }) {
  return (
    <table className="tbl detail-tbl">
      <colgroup>
        <col style={{ width: '64px' }} />
        <col style={{ width: '150px' }} />
        <col style={{ width: '160px' }} />
        <col />
        <col style={{ width: '64px' }} />
        <col style={{ width: '88px' }} />
        <col style={{ width: '92px' }} />
        <col style={{ width: '92px' }} />
        <col style={{ width: '104px' }} />
      </colgroup>
      <thead>
        <tr>
          <th>名次</th>
          <th>队伍</th>
          <th>学校</th>
          <th>成员</th>
          <th className="right">过题</th>
          <th className="right">罚时</th>
          <th className="right">赛前分</th>
          <th className="right">表现分</th>
          <th className="right">变化</th>
        </tr>
      </thead>
      <tbody>
        {teams.map((t, i) => (
          <tr
            key={`${t.rank}-${t.name}-${i}`}
            className={i < 14 ? 'row-rise' : undefined}
            style={i < 14 ? { animationDelay: `${i * 45}ms` } : undefined}
          >
            <td>
              <RankCell rank={t.rank} />
            </td>
            <td>
              <span className="team-name">
                {!t.official ? (
                  <span className="star-mark" title="打星队（非正式排名）">
                    ★
                  </span>
                ) : null}
                {t.name}
              </span>
            </td>
            <td className="muted nowrap">{t.org || '—'}</td>
            <td>
              <MemberList members={t.members} />
            </td>
            <td className="right">{t.solved}</td>
            <td className="right muted">{formatPenalty(t.penalty)}</td>
            <td className="right muted">{t.preRating === null ? '—' : formatScore(t.preRating)}</td>
            <td className="right">
              <span className="score-strong" style={{ fontSize: 16 }}>
                {formatScore(t.perf)}
              </span>
            </td>
            <td className="right">
              <Delta value={t.muDelta} />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function PredictionsTable({ teams }: { teams: ContestTeam[] }) {
  return (
    <table className="tbl detail-tbl">
      <colgroup>
        <col style={{ width: '92px' }} />
        <col style={{ width: '92px' }} />
        <col />
        <col style={{ width: '170px' }} />
        <col style={{ width: '190px' }} />
      </colgroup>
      <thead>
        <tr>
          <th className="right">预测</th>
          <th className="right">实际</th>
          <th>偏差</th>
          <th>队伍</th>
          <th>学校</th>
        </tr>
      </thead>
      <tbody>
        {teams.map((t, i) => {
          // dev > 0 = beat expectation (actual rank better/lower than predicted).
          const dev = t.predictedRank === null ? null : t.predictedRank - t.rank
          return (
            <tr
              key={`${t.rank}-${t.name}-${i}`}
              className={i < 14 ? 'row-rise' : undefined}
              style={i < 14 ? { animationDelay: `${i * 45}ms` } : undefined}
            >
              <td className="right rank" style={{ fontSize: 17 }}>
                {t.predictedRank ?? '—'}
              </td>
              <td className="right rank" style={{ fontSize: 17 }}>
                {t.rank}
              </td>
              <td>
                <Deviation dev={dev} />
              </td>
              <td>
                <span className="team-name">{t.name}</span>
              </td>
              <td className="muted">{t.org || '—'}</td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}

export default function ContestDetailPage() {
  const { slug } = useParams<{ slug: string }>()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()

  const [contest, setContest] = useState<ContestDetail | null>(null)
  const [error, setError] = useState<string | null>(null)

  const tab: ContestTab = isContestTab(searchParams.get('tab'))
    ? (searchParams.get('tab') as ContestTab)
    : 'results'
  // Scoring caliber: 全部 (default) shows the full standings; 仅正式 hides 打星
  // teams and recomputes rank / prediction / perf over the official subset.
  const board: 'all' | 'official' =
    searchParams.get('board') === 'official' ? 'official' : 'all'
  const isOfficial = board === 'official'

  const [loadedSlug, setLoadedSlug] = useState<string | undefined>(undefined)
  if (slug !== loadedSlug) {
    setLoadedSlug(slug)
    setContest(null)
    setError(null)
  }

  const viewKey = `${slug ?? ''}|${tab}|${board}`
  const [pagedView, setPagedView] = useState(viewKey)
  const [page, setPage] = useState(1)
  if (viewKey !== pagedView) {
    setPagedView(viewKey)
    setPage(1)
  }

  useEffect(() => {
    if (!slug) return
    let cancelled = false
    getContest(slug)
      .then((data) => !cancelled && setContest(data))
      .catch((err: unknown) => !cancelled && setError(err instanceof Error ? err.message : '加载失败'))
    return () => {
      cancelled = true
    }
  }, [slug])

  const allTeams = useMemo(() => contest?.teams ?? [], [contest])
  // In 仅正式 mode, drop 打星 teams and swap each row's rank / prediction / perf /
  // preRating / muDelta to the official-only fields so the tables render unchanged.
  const teams = useMemo<ContestTeam[]>(() => {
    if (!isOfficial) return allTeams
    return allTeams
      .filter((t) => t.official)
      .map((t) => ({
        ...t,
        rank: t.rankOfficial ?? t.rank,
        perf: t.perfOfficial,
        preRating: t.preRatingOfficial,
        muDelta: t.muDeltaOfficial,
        predictedRank: t.predictedRankOfficial,
      }))
  }, [allTeams, isOfficial])
  const totalPages = Math.max(1, Math.ceil(teams.length / ROWS_PER_PAGE))
  const clampedPage = Math.min(Math.max(1, page), totalPages)
  const start = (clampedPage - 1) * ROWS_PER_PAGE
  const pageRows = useMemo(() => teams.slice(start, start + ROWS_PER_PAGE), [teams, start])

  function setTab(next: ContestTab) {
    const params = new URLSearchParams(searchParams)
    if (next === 'results') params.delete('tab')
    else params.set('tab', next)
    params.delete('engine')
    setSearchParams(params)
  }

  function selectBoard(next: 'all' | 'official') {
    const params = new URLSearchParams(searchParams)
    if (next === 'official') params.set('board', 'official')
    else params.delete('board')
    setSearchParams(params)
  }

  if (error) {
    return (
      <div className="page-enter">
        <div className="state" role="alert">
          <p className="state__title">加载失败</p>
          <p>{error}</p>
          <p style={{ marginTop: 16 }}>
            <button className="btn" onClick={() => navigate('/contests')}>
              返回比赛列表
            </button>
          </p>
        </div>
      </div>
    )
  }

  if (!contest) {
    return (
      <div className="page-enter">
        <div className="state" role="status">
          正在加载比赛数据…
        </div>
      </div>
    )
  }

  return (
    <div className="page-enter">
      <section className="wrap" style={{ paddingTop: 40 }}>
        <Link to="/contests" className="crumb">
          <Caret dir="left" size={12} /> 比赛列表
        </Link>
      </section>

      <section className="wrap" style={{ paddingTop: 20, paddingBottom: 36 }}>
        <div className="detail-head">
          <CatBadge category={contest.category} />
          <h1 className="display detail-title">{contest.title}</h1>
          <div className="detail-meta tnum">
            <span>{categoryLabel(contest.category)}</span>
            <span className="dotsep">·</span>
            <span>{formatDate(contest.startAt)}</span>
            <span className="dotsep">·</span>
            <span>
              {isOfficial ? `${teams.length} 支正式队伍` : `${contest.teamCount} 支队伍`}
            </span>
          </div>
        </div>
      </section>

      <section className="wrap">
        <div className="detail-toolbar">
          <div className="tabs" role="tablist">
            <button
              className={`tab ${tab === 'results' ? 'is-active' : ''}`}
              role="tab"
              aria-selected={tab === 'results'}
              onClick={() => setTab('results')}
            >
              结果
            </button>
            <button
              className={`tab ${tab === 'prediction' ? 'is-active' : ''}`}
              role="tab"
              aria-selected={tab === 'prediction'}
              onClick={() => setTab('prediction')}
            >
              预测
            </button>
          </div>
          <div className="caliber">
            <span className="caliber__label">计分口径</span>
            <div className="caliber__set" role="tablist" aria-label="计分口径">
              <button
                type="button"
                role="tab"
                aria-selected={!isOfficial}
                className={`caliber__tab ${!isOfficial ? 'is-active' : ''}`}
                onClick={() => selectBoard('all')}
              >
                全部
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={isOfficial}
                className={`caliber__tab ${isOfficial ? 'is-active' : ''}`}
                onClick={() => selectBoard('official')}
              >
                仅正式
              </button>
            </div>
          </div>
        </div>
      </section>

      <section className="wrap" style={{ paddingTop: 8, paddingBottom: 72 }}>
        <div className="board-card" style={{ marginTop: 18 }} key={tab}>
          <div className="tabpane table-scroll">
            {tab === 'results' ? (
              <ResultsTable teams={pageRows} />
            ) : (
              <PredictionsTable teams={pageRows} />
            )}
          </div>
        </div>

        {tab === 'prediction' ? (
          <p className="legend">
            <span className="legend__item">
              <span className="delta delta--up">
                <span className="tri">▲</span>
              </span>{' '}
              优于预期
            </span>
            <span className="legend__item">
              <span className="delta delta--down">
                <span className="tri">▼</span>
              </span>{' '}
              低于预期
            </span>
            <span className="legend__item">
              <span className="delta delta--flat">—</span> 与预期一致
            </span>
          </p>
        ) : null}

        {teams.length > ROWS_PER_PAGE ? (
          <div className="pager">
            <span>
              第 <span className="tnum">{start + 1}–{start + pageRows.length}</span> 项，共{' '}
              <span className="tnum">{teams.length}</span> 项
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
      </section>
    </div>
  )
}
