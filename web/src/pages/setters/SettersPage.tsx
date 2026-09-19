import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  getAllProblemsIndex,
  getContestsIndex,
  type ContestIndexEntry,
  type ProblemIndexRow,
} from '../../lib/data'
import { Caret, Reveal } from '../../components/ui'
import { SETTER_GROUPS, buildSetterIndex, contestSlugsForSetterGroups } from './settersPresentation'
import { SetterWordCloud } from './SetterWordCloud'
import './setters.css'

export default function SettersPage() {
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

  const rows = useMemo(
    () => (contests ? buildSetterIndex(SETTER_GROUPS, contests) : []),
    [contests],
  )
  const contestCount = useMemo(
    () => rows.reduce((sum, row) => sum + row.contestCount, 0),
    [rows],
  )
  const slugs = useMemo(
    () => (contests ? contestSlugsForSetterGroups(SETTER_GROUPS, contests) : null),
    [contests],
  )

  return (
    <div className="page-enter">
      <section className="wrap phead">
        <span className="eyebrow eyebrow--oxford">命题档案</span>
        <h1 className="display">出题组</h1>
        <p className="subtle">
          目前收录 {rows.length || '—'} 个出题组、{contestCount || '—'} 场已确认比赛。
          点进一组查看它出过的场次。
        </p>
        {error ? null : <SetterWordCloud problems={problems} slugs={slugs} />}
      </section>

      {error ? (
        <div className="state" role="alert">
          <p className="state__title">加载失败</p>
          <p>{error}</p>
        </div>
      ) : contests === null ? (
        <div className="state" role="status">
          正在加载出题组…
        </div>
      ) : rows.length === 0 ? (
        <div className="state" role="status">
          <p className="state__title">暂无出题组</p>
          <p>还没有已确认的出题记录。</p>
        </div>
      ) : (
        <section className="wrap" style={{ paddingBottom: 40 }}>
          <div className="clist">
            {rows.map((row) => (
              <Reveal
                as="div"
                className="crow"
                key={row.id}
                role="link"
                tabIndex={0}
                onClick={() => navigate(`/setter/${row.id}`)}
                onKeyDown={(e) => e.key === 'Enter' && navigate(`/setter/${row.id}`)}
              >
                <span className="crow__date tnum">{row.yearLabel}</span>
                <span className="crow__title">{row.name}</span>
                <span className="crow__cat" />
                <span className="crow__teams tnum">
                  <b>{row.contestCount}</b> 场
                </span>
                <span className="crow__go">
                  <Caret dir="right" size={13} />
                </span>
              </Reveal>
            ))}
          </div>
        </section>
      )}
    </div>
  )
}
