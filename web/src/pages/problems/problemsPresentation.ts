import type { ProblemIndexRow, SkillAxisKey } from '../../lib/data'

export type { ProblemIndexRow }

export interface ProblemFilters {
  contest?: string
  year?: string
  type?: SkillAxisKey | ''
  difficulty?: DifficultyKey | ''
  query?: string
}

export type DifficultyKey = 'veryEasy' | 'easy' | 'easyMid' | 'mid' | 'midHard' | 'hard' | 'veryHard' | 'unknown'

export interface DifficultyOption {
  key: DifficultyKey
  label: string
  shortLabel: string
}

export type ProblemSortKey =
  | 'date'
  | 'title'
  | 'contest'
  | 'year'
  | 'type'
  | 'difficulty'
  | 'problemRating'

export type ProblemSortDirection = 'asc' | 'desc'

export const DIFFICULTIES: readonly DifficultyOption[] = [
  { key: 'veryEasy', label: 'Very Easy', shortLabel: 'Very Easy' },
  { key: 'easy', label: 'Easy', shortLabel: 'Easy' },
  { key: 'easyMid', label: 'Easy-Mid', shortLabel: 'Easy-Mid' },
  { key: 'mid', label: 'Mid', shortLabel: 'Mid' },
  { key: 'midHard', label: 'Mid-Hard', shortLabel: 'Mid-Hard' },
  { key: 'hard', label: 'Hard', shortLabel: 'Hard' },
  { key: 'veryHard', label: 'Very Hard', shortLabel: 'Very Hard' },
  { key: 'unknown', label: '未知', shortLabel: '未知' },
]

/** Upper bounds for the seven problem-rating bands (rating increases with difficulty). */
export const PROBLEM_RATING_THRESHOLDS = {
  veryEasyMax: 1300,
  easyMax: 1500,
  easyMidMax: 1800,
  midMax: 1950,
  midHardMax: 2150,
  hardMax: 2350,
} as const

export { SKILL_AXIS_LABELS as AXIS_LABELS } from '../../lib/data'

/** Map a calibrated problem rating to the seven-level explorer difficulty. */
export function difficultyFromProblemRating(rating: number | null | undefined): DifficultyOption {
  if (typeof rating !== 'number' || !Number.isFinite(rating)) return DIFFICULTIES[7]
  if (rating < PROBLEM_RATING_THRESHOLDS.veryEasyMax) return DIFFICULTIES[0]
  if (rating < PROBLEM_RATING_THRESHOLDS.easyMax) return DIFFICULTIES[1]
  if (rating < PROBLEM_RATING_THRESHOLDS.easyMidMax) return DIFFICULTIES[2]
  if (rating < PROBLEM_RATING_THRESHOLDS.midMax) return DIFFICULTIES[3]
  if (rating < PROBLEM_RATING_THRESHOLDS.midHardMax) return DIFFICULTIES[4]
  if (rating < PROBLEM_RATING_THRESHOLDS.hardMax) return DIFFICULTIES[5]
  return DIFFICULTIES[6]
}

export function formatProblemTitle(row: Pick<ProblemIndexRow, 'alias' | 'title'>): string {
  const title = row.title?.trim() || '未命名题目'
  return `${row.alias} · ${title}`
}

/** Display only the calibrated problem score; uncertainty is intentionally omitted. */
export function formatProblemScore(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—'
  return String(Math.round(value))
}

export function problemYear(row: Pick<ProblemIndexRow, 'startAt'>): string {
  const year = new Date(row.startAt).getFullYear()
  return Number.isFinite(year) ? String(year) : ''
}

export function sortProblems(
  rows: readonly ProblemIndexRow[],
  sortKey: ProblemSortKey = 'date',
  direction: ProblemSortDirection = 'desc',
): ProblemIndexRow[] {
  const multiplier = direction === 'asc' ? 1 : -1
  const difficultyRank: Record<DifficultyKey, number> = {
    veryEasy: 0,
    easy: 1,
    easyMid: 2,
    mid: 3,
    midHard: 4,
    hard: 5,
    veryHard: 6,
    unknown: 7,
  }
  const compareNullable = (left: number | null | undefined, right: number | null | undefined): number => {
    const leftMissing = left === null || left === undefined || !Number.isFinite(left)
    const rightMissing = right === null || right === undefined || !Number.isFinite(right)
    if (leftMissing && rightMissing) return 0
    if (leftMissing) return 1
    if (rightMissing) return -1
    return (left - right) * multiplier
  }

  return [...rows].sort((a, b) => {
    let result: number
    switch (sortKey) {
      case 'title':
        result = (a.title?.trim() || '未命名题目').localeCompare(b.title?.trim() || '未命名题目', 'zh-CN') * multiplier
        break
      case 'contest':
        result = a.contestTitle.localeCompare(b.contestTitle, 'zh-CN') * multiplier
        break
      case 'year':
        result = compareNullable(Number(problemYear(a)), Number(problemYear(b)))
        break
      case 'type':
        result = a.typeLabels.join('、').localeCompare(b.typeLabels.join('、'), 'zh-CN') * multiplier
        break
      case 'difficulty':
        {
          const leftDifficulty = difficultyFromProblemRating(a.problemRating).key
          const rightDifficulty = difficultyFromProblemRating(b.problemRating).key
          if (leftDifficulty === 'unknown' && rightDifficulty !== 'unknown') result = 1
          else if (leftDifficulty !== 'unknown' && rightDifficulty === 'unknown') result = -1
          else result = (difficultyRank[leftDifficulty] - difficultyRank[rightDifficulty]) * multiplier
        }
        break
      case 'problemRating':
        result = compareNullable(a.problemRating, b.problemRating)
        break
      case 'date':
      default:
        result = compareNullable(new Date(a.startAt).getTime(), new Date(b.startAt).getTime())
        break
    }
    if (result) return result
    const contest = a.contestTitle.localeCompare(b.contestTitle, 'zh-CN')
    if (contest) return contest
    return a.alias.localeCompare(b.alias, 'en')
  })
}

export function filterProblems(rows: readonly ProblemIndexRow[], filters: ProblemFilters): ProblemIndexRow[] {
  const query = filters.query?.trim().toLocaleLowerCase() ?? ''
  return rows.filter((row) => {
    if (filters.contest && row.contestSlug !== filters.contest) return false
    if (filters.year && problemYear(row) !== filters.year) return false
    if (filters.type && !row.typeKeys.includes(filters.type)) return false
    if (filters.difficulty && difficultyFromProblemRating(row.problemRating).key !== filters.difficulty) return false
    if (query) {
      const haystack = `${row.alias} ${row.title ?? ''} ${row.contestTitle} ${row.canonicalId ?? ''}`.toLocaleLowerCase()
      if (!haystack.includes(query)) return false
    }
    return true
  })
}

export function categoryLabel(category: string): string {
  if (category === 'icpc') return 'ICPC'
  if (category === 'ccpc') return 'CCPC'
  return '省赛'
}
