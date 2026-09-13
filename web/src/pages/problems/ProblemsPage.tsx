import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { getProblemsIndex, type ProblemIndexRow, type SkillAxisKey } from '../../lib/data'
import { SearchIcon } from '../../components/ui'
import {
  AXIS_LABELS,
  DIFFICULTIES,
  categoryLabel,
  difficultyFromProblemRating,
  filterProblems,
  formatProblemScore,
  formatProblemTitle,
  problemYear,
  sortProblems,
  type DifficultyKey,
  type ProblemFilters,
  type ProblemSortDirection,
  type ProblemSortKey,
} from './problemsPresentation'
import './problems.css'

const PAGE_SIZE = 80
const AXES = Object.entries(AXIS_LABELS) as [SkillAxisKey, string][]

function readAxis(value: string | null): SkillAxisKey | '' {
  return AXES.some(([key]) => key === value) ? value as SkillAxisKey : ''
}

function readDifficulty(value: string | null): DifficultyKey | '' {
  return DIFFICULTIES.some((item) => item.key === value) ? value as DifficultyKey : ''
}

const SORT_KEYS: readonly ProblemSortKey[] = ['date', 'title', 'contest', 'year', 'type', 'difficulty', 'problemRating']

function readSortKey(value: string | null): ProblemSortKey {
  return SORT_KEYS.includes(value as ProblemSortKey) ? value as ProblemSortKey : 'date'
}

function readSortDirection(value: string | null): ProblemSortDirection {
  return value === 'asc' ? 'asc' : 'desc'
}

function SortHeader({
  label,
  sortKey,
  activeKey,
  direction,
  onSort,
  align = false,
}: {
  label: string
  sortKey: ProblemSortKey
  activeKey: ProblemSortKey
  direction: ProblemSortDirection
  onSort: (key: ProblemSortKey) => void
  align?: boolean
}) {
  const active = activeKey === sortKey
  return (
    <th className={align ? 'right' : undefined} aria-sort={active ? direction === 'asc' ? 'ascending' : 'descending' : 'none'}>
      <button
        type="button"
        className={`problems-sort-button${active ? ' is-active' : ''}`}
        onClick={() => onSort(sortKey)}
        aria-label={`按${label}${active && direction === 'desc' ? '升序' : '降序'}排序`}
      >
        <span>{label}</span>
        <span className="problems-sort-icon" aria-hidden="true">{active ? direction === 'asc' ? '↑' : '↓' : '↕'}</span>
      </button>
    </th>
  )
}

export default function ProblemsPage() {
  const [params, setParams] = useSearchParams()
  const [rows, setRows] = useState<ProblemIndexRow[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const query = params.get('q') ?? ''
  const contest = params.get('contest') ?? ''
  const year = params.get('year') ?? ''
  const type = readAxis(params.get('type'))
  const difficulty = readDifficulty(params.get('difficulty'))
  const sortKey = readSortKey(params.get('sort'))
  const sortDirection = readSortDirection(params.get('order'))
  const filters: ProblemFilters = { contest, year, type, difficulty }
  const pageParam = Number(params.get('page'))
  const requestedPage = Number.isFinite(pageParam) && pageParam > 0 ? Math.floor(pageParam) : 1

  useEffect(() => {
    let cancelled = false
    getProblemsIndex().then((items) => { if (!cancelled) setRows(items) }).catch((reason: unknown) => {
      if (!cancelled) setError(reason instanceof Error ? reason.message : '题库加载失败。')
    })
    return () => { cancelled = true }
  }, [])

  const filtered = useMemo(() => rows ? sortProblems(filterProblems(rows, { contest, year, type, difficulty, query }), sortKey, sortDirection) : [], [rows, contest, year, type, difficulty, query, sortKey, sortDirection])
  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))
  const page = Math.min(requestedPage, totalPages)
  const visible = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)
  const years = useMemo(() => rows ? [...new Set(rows.map(problemYear).filter(Boolean))].sort((a, b) => Number(b) - Number(a)) : [], [rows])
  const contests = useMemo(() => rows ? [...new Map(rows.map((row) => [row.contestSlug, row.contestTitle])).entries()].sort((a, b) => a[1].localeCompare(b[1], 'zh-CN')) : [], [rows])

  function update(updates: Record<string, string | null>) {
    setParams((previous) => {
      const next = new URLSearchParams(previous)
      Object.entries(updates).forEach(([key, value]) => value ? next.set(key, value) : next.delete(key))
      if (!('page' in updates)) next.delete('page')
      return next
    }, { replace: true })
  }

  function selectSort(nextKey: ProblemSortKey) {
    const nextDirection = nextKey === sortKey ? sortDirection === 'asc' ? 'desc' : 'asc' : nextKey === 'title' || nextKey === 'contest' || nextKey === 'type' ? 'asc' : 'desc'
    update({ sort: nextKey, order: nextDirection })
  }

  return <div className="page-enter problems-page">
    <section className="wrap phead problems-head">
      <span className="eyebrow eyebrow--oxford">题库索引</span>
      <h1 className="display">题目浏览</h1>
    </section>

    <section className="wrap problems-content">
      <div className="problems-filter-panel">
        <div className="problems-search"><SearchIcon size={16} /><input value={query} onChange={(event) => update({ q: event.target.value || null })} placeholder="搜索题目名称、题号或比赛" aria-label="搜索题目名称、题号或比赛" /></div>
        <div className="problems-selects">
          <label>比赛<select value={filters.contest} onChange={(event) => update({ contest: event.target.value || null })}><option value="">全部比赛</option>{contests.map(([slug, title]) => <option key={slug} value={slug}>{title}</option>)}</select></label>
          <label>年份<select value={filters.year} onChange={(event) => update({ year: event.target.value || null })}><option value="">全部年份</option>{years.map((year) => <option key={year} value={year}>{year}</option>)}</select></label>
          <label>题目类型<select value={filters.type} onChange={(event) => update({ type: event.target.value || null })}><option value="">全部类型</option>{AXES.map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
          <label>难度<select value={filters.difficulty} onChange={(event) => update({ difficulty: event.target.value || null })}><option value="">全部难度</option>{DIFFICULTIES.map((item) => <option key={item.key} value={item.key}>{item.label}</option>)}</select></label>
        </div>
        {(query || filters.contest || filters.year || filters.type || filters.difficulty) && <div className="problems-filter-footer"><span className="problems-filter-hint">筛选条件会保存在地址栏，可直接分享当前结果。</span><button type="button" className="problems-clear" onClick={() => setParams({}, { replace: false })}>清除筛选</button></div>}
      </div>

      {error ? <div className="state" role="alert"><p className="state__title">无法加载题库</p><p>{error}</p></div> : rows === null ? <div className="state" role="status">正在加载题库…</div> : filtered.length === 0 ? <div className="state" role="status"><p className="state__title">没有匹配的题目</p><p>试试清空筛选条件或换一个关键词。</p></div> : <>
        <div className="problems-result-bar"><span>共 <b className="tnum">{filtered.length.toLocaleString('zh-CN')}</b> 道题</span><span className="problems-page-no">第 {page} / {totalPages} 页</span></div>
        <div className="problems-table-card"><div className="table-scroll"><table className="tbl problems-table"><thead><tr><SortHeader label="题目" sortKey="title" activeKey={sortKey} direction={sortDirection} onSort={selectSort}/><SortHeader label="比赛" sortKey="contest" activeKey={sortKey} direction={sortDirection} onSort={selectSort}/><SortHeader label="年份" sortKey="year" activeKey={sortKey} direction={sortDirection} onSort={selectSort}/><SortHeader label="题型" sortKey="type" activeKey={sortKey} direction={sortDirection} onSort={selectSort}/><SortHeader label="难度" sortKey="difficulty" activeKey={sortKey} direction={sortDirection} onSort={selectSort}/><SortHeader label="题目 Rating" sortKey="problemRating" activeKey={sortKey} direction={sortDirection} onSort={selectSort} align/><th className="right">通过率</th></tr></thead><tbody>{visible.map((row) => { const difficulty = difficultyFromProblemRating(row.problemRating); return <tr key={`${row.contestSlug}:${row.alias}`}><td>{row.problemUrl ? <a className="problem-title problem-title--link" href={row.problemUrl} target="_blank" rel="noreferrer" aria-label={`打开题目：${formatProblemTitle(row)}`}>{formatProblemTitle(row)}<span className="problem-external" aria-hidden="true">↗</span></a> : <span className="problem-title">{formatProblemTitle(row)}</span>}{row.canonicalId && <span className="problem-id">{row.canonicalId}</span>}</td><td><Link className="problem-contest" to={`/contest/${row.contestSlug}`}>{row.contestTitle}</Link><span className={`problem-category problem-category--${row.category}`}>{categoryLabel(row.category)}</span></td><td className="tnum">{problemYear(row) || '—'}</td><td><div className="problem-tags problem-tags--broad" aria-label="粗略题型">{row.typeLabels.length ? row.typeLabels.map((label) => <span key={label}>{label}</span>) : <span className="muted">未分类</span>}</div>{row.detailTags?.length ? <div className="problem-tags problem-tags--detail" aria-label="具体算法">{row.detailTags.map((tag) => <span key={tag}>{tag}</span>)}</div> : null}</td><td><span className={`difficulty-pill difficulty-pill--${difficulty.key}`}>{difficulty.label}</span></td><td className="right tnum problem-score">{formatProblemScore(row.problemRating)}</td><td className="right tnum">{typeof row.solveRate === 'number' ? `${(row.solveRate * 100).toFixed(0)}%` : '—'}</td></tr> })}</tbody></table></div></div>
        {totalPages > 1 && <nav className="problems-pagination" aria-label="题目分页"><button type="button" disabled={page <= 1} onClick={() => update({ page: String(page - 1) })}>上一页</button><span>{page} / {totalPages}</span><button type="button" disabled={page >= totalPages} onClick={() => update({ page: String(page + 1) })}>下一页</button></nav>}
      </>}
    </section>
  </div>
}
