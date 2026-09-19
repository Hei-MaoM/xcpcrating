import { useMemo } from 'react'
import type { ProblemIndexRow } from '../../lib/data'
import { countAlgorithmTags, scaleTagWeights } from './settersPresentation'

export function SetterWordCloud({
  problems,
  slugs,
}: {
  problems: readonly ProblemIndexRow[] | null
  slugs: ReadonlySet<string> | null
}) {
  const items = useMemo(() => {
    if (!problems || !slugs) return null
    return scaleTagWeights(countAlgorithmTags(problems, slugs))
  }, [problems, slugs])

  if (items === null) {
    return (
      <section className="setter-cloud" aria-busy="true" aria-label="算法词云">
        <p className="setter-cloud__status">正在统计算法标签…</p>
      </section>
    )
  }

  if (items.length === 0) {
    return (
      <section className="setter-cloud" aria-label="算法词云">
        <p className="setter-cloud__status">还没有可用的算法标签。</p>
      </section>
    )
  }

  return (
    <section className="setter-cloud" aria-label="算法词云">
      <div className="setter-cloud__head">
        <span className="setter-cloud__kicker">算法词云</span>
        <span className="setter-cloud__meta tnum">{items.length} 个标签</span>
      </div>
      <div className="setter-cloud__words">
        {items.map((item) => (
          <span
            key={item.tag}
            className={`setter-cloud__word setter-cloud__word--${item.tone}`}
            style={{
              fontSize: `${item.fontSize}px`,
              fontWeight: item.weight,
              opacity: item.opacity,
            }}
            title={`${item.tag} · ${item.count} 题`}
            aria-label={`${item.tag}，${item.count} 题`}
          >
            {item.tag}
          </span>
        ))}
      </div>
    </section>
  )
}
