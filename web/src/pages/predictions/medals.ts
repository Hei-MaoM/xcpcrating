export type PredictionMedal = 'gold' | 'silver' | 'bronze'
export type PredictionRankingMethod = 'rating' | 'medals'

export interface PredictionMedalCounts {
  gold: number
  silver: number
  bronze: number
}

interface PredictionRankFields {
  number: number
  officialRank: number | null
  medalRank?: number | null
}

export interface PredictionRankingRow<T> {
  team: T
  rank: number | null
  medal: PredictionMedal | null
}

/**
 * Predicted medal quantities for the official field. Gold is 10% of official
 * teams rounded up; silver and bronze receive two and three times that many
 * slots respectively.
 */
export function predictionMedalCounts(
  officialTeamCount: number,
): PredictionMedalCounts {
  const eligible = Math.max(0, Math.trunc(officialTeamCount))
  const gold = Math.ceil(eligible * 0.1)
  const silver = Math.min(eligible - gold, gold * 2)
  const bronze = Math.min(eligible - gold - silver, gold * 3)
  return {
    gold,
    silver: Math.max(0, silver),
    bronze: Math.max(0, bronze),
  }
}

/** Return the medal for a one-based position, or null outside the slots. */
export function predictionMedalForPosition(
  position: number | null,
  officialTeamCount: number,
): PredictionMedal | null {
  if (position === null || position < 1) return null

  const counts = predictionMedalCounts(officialTeamCount)
  if (position <= counts.gold) return 'gold'
  if (position <= counts.gold + counts.silver) return 'silver'
  if (position <= counts.gold + counts.silver + counts.bronze) return 'bronze'
  return null
}

function displayedRank(
  team: PredictionRankFields,
  method: PredictionRankingMethod,
): number | null {
  return method === 'rating'
    ? team.officialRank
    : (team.medalRank ?? team.officialRank)
}

/**
 * Sort official teams for one prediction method and assign fixed medal slots.
 * Displayed ranks may tie; medals deliberately use the stable sorted position.
 */
export function predictionRankingRows<T extends PredictionRankFields>(
  teams: readonly T[],
  method: PredictionRankingMethod,
  officialTeamCount: number,
): PredictionRankingRow<T>[] {
  return [...teams]
    .sort((a, b) => {
      const rankA = displayedRank(a, method)
      const rankB = displayedRank(b, method)
      return (
        (rankA ?? Number.MAX_SAFE_INTEGER) -
          (rankB ?? Number.MAX_SAFE_INTEGER) ||
        a.number - b.number
      )
    })
    .map((team, index) => ({
      team,
      rank: displayedRank(team, method),
      medal: predictionMedalForPosition(index + 1, officialTeamCount),
    }))
}
