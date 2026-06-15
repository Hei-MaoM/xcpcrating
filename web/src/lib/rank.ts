/*
 * Competition ranking helper shared by every leaderboard view. Given scores
 * already ordered best-first, assign 1-based "1224" ranks where rows whose scores
 * round to the same whole number share a rank (two tied at 1 → the next is 3).
 *
 * Rounding is monotonic, so in a best-first ordering equal rounded scores are
 * always contiguous — a single forward pass produces correct ties.
 */
export function tiedRanks(scoresBestFirst: ReadonlyArray<number>): number[] {
  const ranks: number[] = []
  let prevRounded: number | null = null
  let prevRank = 0
  scoresBestFirst.forEach((score, i) => {
    const rounded = Math.round(score)
    const rank = prevRounded !== null && rounded === prevRounded ? prevRank : i + 1
    ranks.push(rank)
    prevRounded = rounded
    prevRank = rank
  })
  return ranks
}
