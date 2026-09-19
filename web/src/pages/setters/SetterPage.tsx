import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  getAllProblemsIndex,
  getContestsIndex,
  type ContestIndexEntry,
  type ProblemIndexRow,
} from '../../lib/data'
import { formatDate } from '../../lib/format'
import { Caret, Reveal } from '../../components/ui'
import { contestCategoryBadgeLabel } from '../contests/categories'
import { SETTER_GROUPS, buildSetterDetail } from './settersPresentation'
import { SetterWordCloud } from './SetterWordCloud'
import './setters.css'

function CatBadge({ contest }: { contest: ContestIndexEntry }) {
  const { category } = contest
  const cls =
    category === 'icpc' ? 'icpc' : category === 'ccpc' ? 'ccpc' : 'prov'
  return (
    <span className={`badge badge--${cls}`}>
      {contestCategoryBadgeLabel(contest)}
    </span>
  )
}

export default function SetterPage() {
  const params = useParams()
  const id = params.id ?? ''
  return <SetterPageView key={id} id={id} />
}

function SetterPageView({ id }: { id: string }) {
  const navigate = useNavigate()
  const [contests, setContests] = useState<ContestIndexEntry[] | null>(null)
  const [problems, setProblems] = useState<ProblemIndexRow[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    getContestsIndex()
      .then((data) => {
        if (active) setContests(data)
      })
      .catch((err: unknown) => {
        if (active) setError(err instanceof Error ? err.message : '加载失败')
      })
    getAllProblemsIndex()
      .then((data) => {
        if (active) setProblems(data)
      })
      .catch(() => {
        if (active) setProblems([])
      })
    return () => {
      active = false
    }
  }, [])

  const detail = useMemo(
    () => (contests ? buildSetterDetail(SETTER_GROUPS, contests, id) : null),
    [contests, id],
  )
  const slugs = useMemo(
    () => (detail ? new Set(detail.contests.map((contest) => contest.slug)) : null),
    [detail],
  )

  if (error) {
    return (
      <div className="page-enter">
        <div className="state" role="alert">
          <p className="state__title">加载失败</p>
          <p>{error}</p>
        </div>
      </div>
    )
  }

  if (contests === null) {
    return (
      <div className="page-enter">
        <div className="state" role="status">
          正在加载出题组…
        </div>
      </div>
    )
  }

  if (!detail) {
    return (
      <div className="page-enter">
        <div className="state" role="status">
          <p className="state__title">未找到该出题组</p>
          <p>
            <Link to="/setters" className="crumb">
              <Caret dir="left" size={12} /> 返回出题组
            </Link>
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="page-enter">
      <section className="wrap" style={{ paddingTop: 40 }}>
        <Link to="/setters" className="crumb">
          <Caret dir="left" size={12} /> 出题组
        </Link>
      </section>

      <section className="wrap phead setter-head">
        <span className="eyebrow eyebrow--oxford">出题组</span>
        <h1 className="display">{detail.name}</h1>
        <div className="school-stats">
          <div className="school-stat">
            <span className="school-stat__label">场次</span>
            <span className="school-stat__value tnum">{detail.contests.length}</span>
          </div>
          <div className="school-stat">
            <span className="school-stat__label">年份</span>
            <span className="school-stat__value tnum">{detail.yearLabel}</span>
          </div>
        </div>
        <SetterWordCloud problems={problems} slugs={slugs} />
      </section>

      <section className="wrap" style={{ paddingBottom: 40 }}>
        <div className="clist">
          {detail.contests.map((contest) => (
            <Reveal
              as="div"
              className="crow"
              key={contest.slug}
              role="link"
              tabIndex={0}
              onClick={() => navigate(`/contest/${contest.slug}`)}
              onKeyDown={(e) =>
                e.key === 'Enter' && navigate(`/contest/${contest.slug}`)
              }
            >
              <span className="crow__date tnum">{formatDate(contest.startAt)}</span>
              <span className="crow__title">{contest.title}</span>
              <span className="crow__cat">
                <CatBadge contest={contest} />
              </span>
              <span className="crow__teams tnum">
                <b>{contest.teamCount}</b> 队
              </span>
              <span className="crow__go">
                <Caret dir="right" size={13} />
              </span>
            </Reveal>
          ))}
        </div>
      </section>
    </div>
  )
}
