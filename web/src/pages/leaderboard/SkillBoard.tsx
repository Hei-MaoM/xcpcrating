import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import {
  SKILL_AXIS_LABELS,
  SKILL_AXIS_ORDER,
  type SkillAxisKey,
} from '../../lib/data'
import { SearchIcon } from '../../components/ui'
import { Pagination } from '../../components/ui/Pagination'
import { GradeBadge } from '../../components/ui/GradeBadge'
import {
  skillLeaderboardEmptyMessage,
  formatSkillTopPercent,
  type SkillLeaderboardMode,
  type SkillLeaderboardRow,
} from './skillBoardPresentation'
import { querySkillBoard } from './skillBoardWorker'
import './skillBoard.css'

const PAGE_SIZE = 30
const TIER = 'overall' as const

type LoadState =
  | { status: 'loading' }
  | { status: 'ready'; key: string; rows: SkillLeaderboardRow[]; total: number; totalPages: number; page: number }
  | { status: 'unavailable' }
  | { status: 'error'; message: string }

/** Official participation is the site-wide default caliber for this board. */
const MODE: SkillLeaderboardMode = 'official'

function readAxis(value: string | null): SkillAxisKey {
  return SKILL_AXIS_ORDER.includes(value as SkillAxisKey) ? (value as SkillAxisKey) : SKILL_AXIS_ORDER[0]
}

function readPage(value: string | null): number {
  const page = Number(value)
  return Number.isFinite(page) && page >= 1 ? Math.floor(page) : 1
}

/**
 * The thirteen-dimension board shown as a tab on the home page. One of the
 * dimensions is selected at a time; the board always uses the official
 * participation caliber, so no extra caliber row is rendered.
 */
export function SkillBoard() {
  const [searchParams, setSearchParams] = useSearchParams()
  const mode = MODE
  const axis = readAxis(searchParams.get('axis'))
  const requestedPage = readPage(searchParams.get('page'))
  const query = searchParams.get('q') ?? ''
  const [state, setState] = useState<LoadState>({ status: 'loading' })
  const requestKey = `${mode}:${TIER}:${axis}`

  useEffect(() => {
    let cancelled = false
    // The worker fetches, decodes and ranks the ~6 MB axis board and answers
    // with one page, so the main thread never materialises 47k rows.
    querySkillBoard({ mode, tier: TIER, axis, query, page: requestedPage, pageSize: PAGE_SIZE })
      .then((result) => {
        if (cancelled) return
        setState({
          status: 'ready',
          key: requestKey,
          rows: result.rows,
          total: result.total,
          totalPages: result.totalPages,
          page: result.page,
        })
      })
      .catch((error: unknown) => {
        if (!cancelled) setState({ status: 'error', message: error instanceof Error ? error.message : '题型排行榜加载失败。' })
      })
    return () => {
      cancelled = true
    }
  }, [axis, mode, query, requestKey, requestedPage])

  const isPending = state.status === 'loading' || (state.status === 'ready' && state.key !== requestKey)
  const rows = state.status === 'ready' && state.key === requestKey ? state.rows : []
  const total = state.status === 'ready' && state.key === requestKey ? state.total : 0
  const totalPages = state.status === 'ready' && state.key === requestKey ? state.totalPages : 1
  const page = state.status === 'ready' && state.key === requestKey ? state.page : requestedPage

  function updateParams(updates: Record<string, string | null>) {
    setSearchParams(
      (previous) => {
        const next = new URLSearchParams(previous)
        Object.entries(updates).forEach(([key, value]) => (value ? next.set(key, value) : next.delete(key)))
        if (!('page' in updates)) next.delete('page')
        return next
      },
      { replace: false },
    )
  }

  return (
    <div className="skill-board">
      <div className="skill-axis-nav" role="tablist" aria-label="十三个题型维度">
        {SKILL_AXIS_ORDER.map((item, index) => (
          <button
            key={item}
            type="button"
            role="tab"
            aria-selected={axis === item}
            className={axis === item ? 'is-active' : ''}
            onClick={() => updateParams({ axis: item })}
          >
            <span>{String(index + 1).padStart(2, '0')}</span>
            {SKILL_AXIS_LABELS[item]}
          </button>
        ))}
      </div>

      <div className="toolbar skill-toolbar">
        <label className="school-search skill-search">
          <SearchIcon size={15} />
          <input
            value={query}
            onChange={(event) => updateParams({ q: event.target.value || null })}
            placeholder="搜索选手、学校或 key"
            aria-label="搜索选手、学校或 key"
          />
        </label>
        <span className="toolbar__count">
          共 <span className="tnum">{total.toLocaleString('en-US')}</span> 位选手
        </span>
      </div>

      <div className="skill-table-heading">
        <div>
          <span className="eyebrow">{SKILL_AXIS_LABELS[axis]}</span>
          <p>按原始题型能力分查看选手排名。</p>
        </div>
        <span className="skill-table-heading__page">
          第 {page} / {totalPages} 页
        </span>
      </div>

      {isPending ? (
        <div className="state" role="status">
          正在加载题型排行榜…
        </div>
      ) : state.status === 'error' ? (
        <div className="state" role="alert">
          <p className="state__title">无法加载题型榜</p>
          <p>{state.message}</p>
        </div>
      ) : state.status === 'unavailable' || rows.length === 0 ? (
        <div className="state" role="status">
          {skillLeaderboardEmptyMessage(state.status === 'unavailable' ? 'unavailable' : 'empty')}
        </div>
      ) : (
        <div className="board-card skill-board-card">
          <div className="table-scroll">
            <table className="tbl board-tbl skill-table">
              <thead>
                <tr>
                  <th>名次</th>
                  <th>选手 / 学校</th>
                  <th className="right">能力 rating</th>
                  <th className="right">同级百分位</th>
                  <th className="right">等级</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.key}>
                    <td>
                      <span className="rank">{row.rank ?? '—'}</span>
                    </td>
                    <td>
                      <Link to={`/player/${encodeURIComponent(row.key)}`} className="player-name skill-player-name">
                        {row.name}
                      </Link>
                      <span className="skill-org">{row.org || '—'}</span>
                    </td>
                    <td className="right">
                      <span className="score-strong">{row.score === null ? '—' : row.score.toFixed(1)}</span>
                    </td>
                    <td className="right tnum">{formatSkillTopPercent(row.topPercent, row.rank)}</td>
                    <td className="right">
                      <GradeBadge grade={row.grade} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination
            page={page}
            pageSize={PAGE_SIZE}
            totalItems={total}
            onPageChange={(nextPage) => updateParams({ page: String(nextPage) })}
          />
        </div>
      )}
      <p className="skill-page-note">
        <strong>说明</strong> 题型分数按核心解法与难度校准生成，题目状态来自队伍榜单，不代表队内个人提交归因。
      </p>
    </div>
  )
}

export default SkillBoard
