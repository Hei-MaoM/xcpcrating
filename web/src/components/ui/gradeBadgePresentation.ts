import type { PanelGrade } from '../../lib/data'

export function gradeClassName(grade: PanelGrade | null): string {
  return `grade-badge--${grade?.toLowerCase() ?? 'empty'}`
}
