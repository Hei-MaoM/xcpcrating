import type { ContestIndexEntry } from '../../lib/data'

export const ALL_COMPETITION_SEASONS = 'all'

export interface CompetitionSeason {
  key: string
  label: string
  startYear: number
}

/** Map a source-local contest date to its September–August season key. */
export function competitionSeasonKey(startAt: string): string | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(startAt)
  if (!match) return null

  const calendarYear = Number(match[1])
  const month = Number(match[2])
  const day = Number(match[3])
  if (
    !Number.isInteger(calendarYear) ||
    month < 1 ||
    month > 12 ||
    day < 1 ||
    day > new Date(Date.UTC(calendarYear, month, 0)).getUTCDate()
  ) {
    return null
  }

  const startYear = month >= 9 ? calendarYear : calendarYear - 1
  return `${startYear}-${startYear + 1}`
}

export function competitionSeasonLabel(key: string): string {
  const match = /^(\d{4})-(\d{4})$/.exec(key)
  if (!match || Number(match[2]) !== Number(match[1]) + 1) return key
  return `${match[1]}–${match[2]}`
}

/** Build newest-first season options from the contests currently available. */
export function listCompetitionSeasons(
  contests: ReadonlyArray<Pick<ContestIndexEntry, 'startAt'>>,
): CompetitionSeason[] {
  const startYears = new Set<number>()
  for (const contest of contests) {
    const key = competitionSeasonKey(contest.startAt)
    if (key) startYears.add(Number(key.slice(0, 4)))
  }

  return [...startYears]
    .sort((left, right) => right - left)
    .map((startYear) => {
      const key = `${startYear}-${startYear + 1}`
      return {
        key,
        label: competitionSeasonLabel(key),
        startYear,
      }
    })
}

/** Resolve a URL selection, falling back to the all-season range. */
export function resolveCompetitionSeason(
  seasons: ReadonlyArray<CompetitionSeason>,
  requested: string | null,
): string {
  if (requested === null || requested === ALL_COMPETITION_SEASONS) {
    return ALL_COMPETITION_SEASONS
  }
  return (
    seasons.find((season) => season.key === requested)?.key ??
    ALL_COMPETITION_SEASONS
  )
}

/** Omit the all-season default from the URL; retain a valid season selection. */
export function serializeCompetitionSeason(
  seasons: ReadonlyArray<CompetitionSeason>,
  selected: string,
): string | null {
  if (
    selected === ALL_COMPETITION_SEASONS ||
    !seasons.some((season) => season.key === selected)
  ) {
    return null
  }
  return selected
}
