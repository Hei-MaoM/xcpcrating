import { useEffect, useMemo, useState } from 'react'
import { useParams, Link, useSearchParams } from 'react-router-dom'
import {
  getPlayer,
  DataError,
  type MedalTier,
  type PlayerDetail,
  type PlayerHistoryEntry,
} from '../../lib/data'
import { formatDate, formatScore } from '../../lib/format'
import { Caret, CountUp, Reveal, RuleDraw } from '../../components/ui'
import { RatingChart } from '../../components/charts/RatingChart'
import { bestRank, careerSpan, sortedByTime } from './stats'

type LoadState =
  | { status: 'loading' }
  | { status: 'ready'; player: PlayerDetail }
  | { status: 'notFound' }
  | { status: 'error'; message: string }

const TIERS: { key: MedalTier; label: string }[] = [
  { key: 'final', label: '决赛' },
  { key: 'regional', label: '区域赛' },
  { key: 'invitational', label: '邀请赛' },
  { key: 'provincial', label: '省赛' },
]

const ZERO = { gold: 0, silver: 0, bronze: 0 }

/** The four-tier medal wall (always shows all tiers; zero counts dim out). */
function MedalWall({ player }: { player: PlayerDetail }) {
  const disc = (n: number, cls: string, label: string) => (
    <div className="mw-pip" style={{ opacity: n === 0 ? 0.34 : 1 }}>
      <i className={`metal metal--${cls}`} style={{ width: 18, height: 18 }} />
      <span className="mw-pip__label">{label}</span>
      <span className={`mw-pip__n ${n === 0 ? 'is-zero' : ''}`}>{n}</span>
    </div>
  )
  return (
    <div className="medal-wall">
      {TIERS.map(({ key, label }) => {
        const m = player.medals?.[key] ?? ZERO
        const total = m.gold + m.silver + m.bronze
        return (
          <Reveal as="div" className="mw-cell" key={key}>
            <div className="mw-cell__top">
              <span className="mw-cell__cat serif">{label}</span>
              <span className="mw-cell__total tnum">
                <CountUp value={total} />
              </span>
            </div>
            <div className="mw-cell__pips">
              {disc(m.gold, 'gold', '金')}
              {disc(m.silver, 'silver', '银')}
              {disc(m.bronze, 'bronze', '铜')}
            </div>
          </Reveal>
        )
      })}
    </div>
  )
}

type BoardKind = 'all' | 'official'

function Dossier({ player }: { player: PlayerDetail }) {
  // Scoring caliber, persisted in the URL (?board=all). Default: 正式参赛.
  const [searchParams, setSearchParams] = useSearchParams()
  const board: BoardKind = searchParams.get('board') === 'all' ? 'all' : 'official'
  const isOfficial = board === 'official'

  function selectBoard(next: BoardKind) {
    setSearchParams(
      (prev) => {
        const merged = new URLSearchParams(prev)
        if (next === 'all') merged.set('board', 'all')
        else merged.delete('board')
        return merged
      },
      { replace: false },
    )
  }

  // Rows that COUNT for the active caliber: all participations, or official-only.
  const officialRows = useMemo(
    () => player.history.filter((h) => h.official),
    [player.history],
  )
  const countedRows = isOfficial ? officialRows : player.history

  const span = careerSpan(countedRows)
  // 最佳名次跟随口径：正式口径取"正式队伍中的名次"，全部口径取全场名次。
  const best = useMemo(() => {
    if (!isOfficial) return bestRank(player.history)
    const ranks = officialRows
      .map((h) => h.rankOfficial)
      .filter((r): r is number => r !== null)
    return ranks.length ? Math.min(...ranks) : null
  }, [isOfficial, player.history, officialRows])
  const contestsCount = isOfficial ? officialRows.length : player.contests

  // Standings come precomputed on the player record — no leaderboard fetch.
  const boardRating = isOfficial ? player.officialRating : player.rating
  const boardRank = isOfficial ? player.officialRank : player.allRank
  const hasBoardRating = boardRating !== null

  // Chart follows the caliber and plots only RATED contests (an unrated /
  // gated-out contest never moved the rating, so it carries no point). Official
  // mode remaps onto the official perf / rating / E metrics.
  const chartHistory = useMemo<PlayerHistoryEntry[]>(() => {
    if (!isOfficial) return player.history.filter((h) => h.rated)
    return officialRows
      .filter((h) => h.ratedOfficial && h.perfOfficial !== null)
      .map((h) => ({
        ...h,
        perf: h.perfOfficial as number,
        rating_after: h.ratingAfterOfficial,
        mu_after: h.muAfterOfficial,
      }))
  }, [isOfficial, player.history, officialRows])

  // History table rows: 正式参赛 lists official contests only (打星 hidden);
  // 全部参赛 lists everything, tagging the 打星 rows.
  const historyDesc = useMemo(
    () => [...sortedByTime(player.history)].reverse(),
    [player.history],
  )
  const tableRows = isOfficial ? historyDesc.filter((h) => h.official) : historyDesc
  const starredCount = player.history.length - officialRows.length

  return (
    <div className="page-enter">
      <section className="wrap dossier-topbar">
        <Link to="/" className="crumb">
          <Caret dir="left" size={12} /> 选手榜单
        </Link>
        <div className="caliber">
          <span className="caliber__label">计分口径</span>
          <div className="caliber__set" role="tablist" aria-label="计分口径">
            <button
              type="button"
              role="tab"
              aria-selected={isOfficial}
              className={`caliber__tab ${isOfficial ? 'is-active' : ''}`}
              onClick={() => selectBoard('official')}
            >
              正式参赛
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={!isOfficial}
              className={`caliber__tab ${!isOfficial ? 'is-active' : ''}`}
              onClick={() => selectBoard('all')}
            >
              全部参赛
            </button>
          </div>
        </div>
      </section>

      {/* hero */}
      <section className="wrap dossier-hero">
        <div className="dossier-id">
          <span className="eyebrow eyebrow--oxford">选手档案</span>
          <h1 className="display dossier-name">{player.name}</h1>
          <div className="dossier-school">{player.org || '—'}</div>
          <div className="stat-row">
            <div className="stat">
              <span className="stat__k">{isOfficial ? '正式场次' : '参赛场次'}</span>
              <span className="stat__v tnum">
                <CountUp value={contestsCount} />
              </span>
            </div>
            <div className="stat">
              <span className="stat__k">最佳名次</span>
              <span className="stat__v">
                {best === null ? '—' : <>第 <CountUp value={best} className="tnum" /></>}
              </span>
            </div>
            <div className="stat">
              <span className="stat__k">生涯跨度</span>
              <span className="stat__v stat__v--sm tnum">
                {formatDate(span.firstAt)} <span className="dim">至</span> {formatDate(span.lastAt)}
              </span>
            </div>
          </div>
        </div>

        <aside className="honor-card">
          <div className="honor-card__rail" />
          <span className="eyebrow">阶梯分 · {isOfficial ? '仅正式参赛' : '全部参赛'}</span>
          <div className="honor-card__num serif tnum">
            {hasBoardRating ? (
              <CountUp value={boardRating ?? 0} decimals={1} duration={1300} />
            ) : (
              '—'
            )}
          </div>
          <div className="honor-card__rank">
            <i className="metal metal--gold" style={{ width: 15, height: 15 }} />
            {hasBoardRating && boardRank !== null ? (
              <>
                积分榜第 <span className="tnum">{boardRank}</span> 位
              </>
            ) : isOfficial ? (
              '无正式参赛记录'
            ) : (
              '场次不足'
            )}
          </div>
        </aside>
      </section>

      {/* medal wall */}
      <section className="wrap" style={{ paddingTop: 8, paddingBottom: 48 }}>
        <div className="section-label">
          <span className="eyebrow">奖牌墙</span>
          <RuleDraw className="section-label__rule" />
        </div>
        <MedalWall player={player} />
      </section>

      {/* trajectory chart */}
      <section className="band--2">
        <div className="wrap" style={{ paddingTop: 56, paddingBottom: 56 }}>
          <div className="chart-head">
            <span
              className="eyebrow eyebrow--oxford"
              style={{ fontSize: 14, letterSpacing: '0.22em' }}
            >
              表现分轨迹
            </span>
            <p className="chart-caption">
              散点为每场表现分，折线为累积阶梯分。
              {isOfficial ? '（仅正式参赛）' : ''}
              <br />
              悬停任意一场查看卷宗。
            </p>
          </div>
          <div className="card chart-card">
            <RatingChart history={chartHistory} rating={boardRating} />
          </div>
        </div>
      </section>

      {/* per-contest history */}
      <section className="wrap" style={{ paddingTop: 56, paddingBottom: 72 }}>
        <div className="section-label">
          <span className="eyebrow">逐场历史</span>
          <RuleDraw className="section-label__rule" />
        </div>
        <div className="board-card" style={{ marginTop: 20 }}>
          <div className="table-scroll">
          <table className="tbl history-tbl">
            <colgroup>
              <col style={{ width: '120px' }} />
              <col />
              <col style={{ width: '160px' }} />
              <col style={{ width: '120px' }} />
              <col style={{ width: '108px' }} />
              <col style={{ width: '110px' }} />
            </colgroup>
            <thead>
              <tr>
                <th>日期</th>
                <th>比赛</th>
                <th>队名</th>
                <th className="right">名次</th>
                <th className="right">表现分</th>
                <th className="right">赛后分</th>
              </tr>
            </thead>
            <tbody>
              {tableRows.map((h, i) => {
                const starred = !h.official
                // Unrated (gated-out) contests didn't count toward the ladder —
                // their 表现分 / 赛后分 render as "—" in the active caliber.
                const isRowRated = isOfficial ? h.ratedOfficial : h.rated
                const perfVal = !isRowRated ? null : isOfficial ? h.perfOfficial : h.perf
                const ratingVal = !isRowRated
                  ? null
                  : isOfficial
                    ? h.ratingAfterOfficial
                    : h.rating_after
                const rankVal = isOfficial ? h.rankOfficial : h.rank
                const teamCountVal = isOfficial ? h.teamCountOfficial : h.teamCount
                return (
                  <tr
                    key={`${h.contestId}-${i}`}
                    className={`row-link ${i < 14 ? 'row-rise' : ''}`}
                    style={i < 14 ? { animationDelay: `${i * 45}ms` } : undefined}
                    tabIndex={0}
                    onClick={() => window.location.assign(`#/contest/${h.contestId}`)}
                    onKeyDown={(e) =>
                      e.key === 'Enter' && window.location.assign(`#/contest/${h.contestId}`)
                    }
                  >
                    <td className="dim tnum">{formatDate(h.startAt)}</td>
                    <td style={{ fontWeight: 500 }}>{h.title}</td>
                    <td className="muted">
                      <span className="team-name" style={{ fontSize: 15 }}>
                        {h.teamName}
                      </span>
                      {starred ? <span className="star-tag">打星</span> : null}
                    </td>
                    <td className="right tnum">
                      {rankVal ?? '—'} <span className="dim">/ {teamCountVal ?? '—'}</span>
                    </td>
                    <td className="right">
                      {perfVal === null ? (
                        <span className="dim">—</span>
                      ) : (
                        <span className="score-strong" style={{ fontSize: 16 }}>
                          {formatScore(perfVal)}
                        </span>
                      )}
                    </td>
                    <td className="right tnum muted">
                      {ratingVal === null ? <span className="dim">—</span> : formatScore(ratingVal)}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
          </div>
          <div className="history-foot">
            {isOfficial
              ? `共 ${officialRows.length} 场正式参赛`
              : `共 ${player.history.length} 场${
                  starredCount > 0 ? ` · 含打星 ${starredCount} 场` : ''
                }`}
          </div>
        </div>
      </section>
    </div>
  )
}

/**
 * Player detail page (route: #/player/:key). Loads the player's shard, then
 * renders the Light Luxury dossier: hero + honor card, medal wall, trajectory
 * chart, and per-contest history. A 404 path handles unknown keys.
 */
export default function PlayerPage() {
  const { key } = useParams<{ key: string }>()
  const [state, setState] = useState<LoadState>({ status: 'loading' })

  const [loadedKey, setLoadedKey] = useState<string | undefined>(undefined)
  if (key !== loadedKey) {
    setLoadedKey(key)
    setState(key ? { status: 'loading' } : { status: 'notFound' })
  }

  useEffect(() => {
    if (!key) return
    let cancelled = false
    getPlayer(key)
      .then((player) => !cancelled && setState({ status: 'ready', player }))
      .catch((error: unknown) => {
        if (cancelled) return
        if (error instanceof DataError && (error.status === undefined || error.status === 404)) {
          setState({ status: 'notFound' })
          return
        }
        setState({
          status: 'error',
          message: error instanceof Error ? error.message : '未知错误，请稍后重试。',
        })
      })
    return () => {
      cancelled = true
    }
  }, [key])

  if (state.status === 'loading') {
    return (
      <div className="page-enter">
        <div className="state" role="status" aria-live="polite">
          <p className="state__title">加载中…</p>
          <p>正在读取选手档案。</p>
        </div>
      </div>
    )
  }

  if (state.status === 'error') {
    return (
      <div className="page-enter">
        <div className="state" role="alert">
          <p className="state__title">加载失败</p>
          <p>{state.message}</p>
          <p style={{ marginTop: 16 }}>
            <Link className="btn" to="/">
              返回榜单
            </Link>
          </p>
        </div>
      </div>
    )
  }

  if (state.status === 'notFound') {
    return (
      <div className="page-enter">
        <div className="state" role="status">
          <p className="state__title">未找到该选手</p>
          <p>
            键值 <code>{key}</code> 在数据集中不存在，可能拼写有误或参赛场次过少未被收录。
          </p>
          <p style={{ marginTop: 16 }}>
            <Link className="btn" to="/">
              去榜单查找
            </Link>
          </p>
        </div>
      </div>
    )
  }

  return <Dossier player={state.player} />
}
