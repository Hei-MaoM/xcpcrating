import type { ContestIndexEntry } from '../../lib/data'
import { formatYear } from '../../lib/format'
import { SETTER_GROUPS, type SetterGroupRecord } from './settersCatalog'

export type { SetterGroupRecord }
export { SETTER_GROUPS }

export interface SetterSummary {
  id: string
  name: string
  contestCount: number
  years: readonly string[]
  yearLabel: string
}

export interface SetterDetail {
  id: string
  name: string
  yearLabel: string
  contests: ContestIndexEntry[]
}

function contestTime(contest: ContestIndexEntry): number {
  const time = new Date(contest.startAt).getTime()
  return Number.isNaN(time) ? 0 : time
}

function yearsOf(contests: readonly ContestIndexEntry[]): string[] {
  const years = new Set<string>()
  for (const contest of contests) {
    const year = formatYear(contest.startAt)
    if (year !== '—') years.add(year)
  }
  return [...years].sort((a, b) => a.localeCompare(b))
}

/** Compact year span: 2025, or 2024–2025. */
export function formatYearSpan(years: readonly string[]): string {
  if (years.length === 0) return '—'
  if (years.length === 1) return years[0]
  return `${years[0]}–${years[years.length - 1]}`
}

function resolveContests(
  contestIds: readonly string[],
  contests: readonly ContestIndexEntry[],
): ContestIndexEntry[] {
  const byId = new Map(contests.map((contest) => [contest.id, contest]))
  const resolved: ContestIndexEntry[] = []
  for (const id of contestIds) {
    const contest = byId.get(id)
    if (contest) resolved.push(contest)
  }
  return resolved.sort((a, b) => contestTime(b) - contestTime(a) || a.title.localeCompare(b.title, 'zh-CN'))
}

/** Navigation rows: groups with at least one known contest, most contests first. */
export function buildSetterIndex(
  groups: readonly SetterGroupRecord[],
  contests: readonly ContestIndexEntry[],
): SetterSummary[] {
  const rows: SetterSummary[] = []
  for (const group of groups) {
    const resolved = resolveContests(group.contestIds, contests)
    if (resolved.length === 0) continue
    const years = yearsOf(resolved)
    rows.push({
      id: group.id,
      name: group.name,
      contestCount: resolved.length,
      years,
      yearLabel: formatYearSpan(years),
    })
  }
  return rows.sort(
    (a, b) =>
      b.contestCount - a.contestCount || a.name.localeCompare(b.name, 'zh-CN'),
  )
}

/** Dedicated group page payload; null when the id is unknown or empty. */
export function buildSetterDetail(
  groups: readonly SetterGroupRecord[],
  contests: readonly ContestIndexEntry[],
  id: string,
): SetterDetail | null {
  const group = groups.find((item) => item.id === id)
  if (!group) return null
  const resolved = resolveContests(group.contestIds, contests)
  if (resolved.length === 0) return null
  return {
    id: group.id,
    name: group.name,
    yearLabel: formatYearSpan(yearsOf(resolved)),
    contests: resolved,
  }
}

export function findSetterByContestId(
  groups: readonly SetterGroupRecord[],
  contestId: string,
): { id: string; name: string } | null {
  for (const group of groups) {
    if (group.contestIds.includes(contestId)) {
      return { id: group.id, name: group.name }
    }
  }
  return null
}

const UNCLASSIFIED = '未分类'

export interface TaggedProblem {
  contestSlug: string
  detailTags?: readonly string[]
  typeLabels?: readonly string[]
}

export interface AlgorithmTagCount {
  tag: string
  count: number
}

export type AlgorithmTagTone = 'hot' | 'mid' | 'cool'

export interface ScaledAlgorithmTag extends AlgorithmTagCount {
  fontSize: number
  weight: 500 | 600 | 700
  opacity: number
  tone: AlgorithmTagTone
}

function normalizeTags(tags: readonly string[] | undefined): string[] {
  const seen = new Set<string>()
  const out: string[] = []
  for (const raw of tags ?? []) {
    const tag = raw.trim()
    if (!tag || tag === UNCLASSIFIED || seen.has(tag)) continue
    seen.add(tag)
    out.push(tag)
  }
  return out
}

/** Fine-grained tags first; coarse axis labels only when those are missing. */
export function algorithmTagsForProblem(
  row: Pick<TaggedProblem, 'detailTags' | 'typeLabels'>,
): string[] {
  const detail = normalizeTags(row.detailTags)
  if (detail.length > 0) return detail
  return normalizeTags(row.typeLabels)
}

/** Slugs of catalog contests that actually exist in the index. */
export function contestSlugsForSetterGroups(
  groups: readonly SetterGroupRecord[],
  contests: readonly ContestIndexEntry[],
): Set<string> {
  const slugs = new Set<string>()
  for (const group of groups) {
    for (const contest of resolveContests(group.contestIds, contests)) {
      slugs.add(contest.slug)
    }
  }
  return slugs
}

/** Frequency of algorithm tags among problems in the given contests. */
export function countAlgorithmTags(
  problems: readonly TaggedProblem[],
  contestSlugs: ReadonlySet<string>,
): AlgorithmTagCount[] {
  const counts = new Map<string, number>()
  for (const problem of problems) {
    if (!contestSlugs.has(problem.contestSlug)) continue
    for (const tag of algorithmTagsForProblem(problem)) {
      counts.set(tag, (counts.get(tag) ?? 0) + 1)
    }
  }
  return [...counts.entries()]
    .map(([tag, count]) => ({ tag, count }))
    .sort((a, b) => b.count - a.count || a.tag.localeCompare(b.tag, 'zh-CN'))
}

function tagTone(t: number): AlgorithmTagTone {
  if (t >= 0.66) return 'hot'
  if (t >= 0.33) return 'mid'
  return 'cool'
}

function tagWeight(t: number): 500 | 600 | 700 {
  if (t >= 0.66) return 700
  if (t >= 0.33) return 600
  return 500
}

/** Map raw counts onto newspaper-scale type. Equal counts sit at the max size. */
export function scaleTagWeights(
  items: readonly AlgorithmTagCount[],
  options?: { minSize?: number; maxSize?: number },
): ScaledAlgorithmTag[] {
  const minSize = options?.minSize ?? 13
  const maxSize = options?.maxSize ?? 38
  if (items.length === 0) return []
  let minCount = Infinity
  let maxCount = -Infinity
  for (const item of items) {
    if (item.count < minCount) minCount = item.count
    if (item.count > maxCount) maxCount = item.count
  }
  return items.map((item) => {
    const t =
      maxCount <= minCount
        ? 1
        : (Math.log(item.count) - Math.log(minCount)) /
          (Math.log(maxCount) - Math.log(minCount))
    return {
      tag: item.tag,
      count: item.count,
      fontSize: Math.round(minSize + t * (maxSize - minSize)),
      weight: tagWeight(t),
      opacity: Math.round((0.54 + t * 0.46) * 100) / 100,
      tone: tagTone(t),
    }
  })
}
