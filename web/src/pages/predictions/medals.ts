export type PredictionMedal = 'gold' | 'silver' | 'bronze'

export interface PredictionMedalCounts {
  gold: number
  silver: number
  bronze: number
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

/** Return the medal for a one-based official rank, or null outside the slots. */
export function predictionMedalForRank(
  officialRank: number | null,
  officialTeamCount: number,
): PredictionMedal | null {
  if (officialRank === null || officialRank < 1) return null

  const counts = predictionMedalCounts(officialTeamCount)
  if (officialRank <= counts.gold) return 'gold'
  if (officialRank <= counts.gold + counts.silver) return 'silver'
  if (officialRank <= counts.gold + counts.silver + counts.bronze) return 'bronze'
  return null
}
