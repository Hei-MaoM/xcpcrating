import type { PanelGrade } from '../../lib/data'
import { gradeClassName } from './gradeBadgePresentation'
import './grade-badge.css'

export function GradeBadge({ grade, emptyText = '—' }: { grade: PanelGrade | null; emptyText?: string }) {
  return (
    <span
      className={`grade-badge grade-badge--compact ${gradeClassName(grade)}`}
      aria-label={grade ? `等级 ${grade}` : '暂无等级'}
    >
      {grade ?? emptyText}
    </span>
  )
}
