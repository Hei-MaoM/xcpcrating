import type { PanelGrade, SkillLeaderboardIndex, SkillLeaderboardIndexRow } from './data'

/**
 * Compact axis-board codec.
 *
 * One axis board is the heaviest payload the site requests (a whole caliber's
 * leaderboard), so the exporter repeats the field names once in ``rowFields``
 * and ships array rows. This module stays dependency-free so the skill-board
 * Web Worker can decode without pulling the whole data layer; ``data.ts``
 * re-exports it for the main-thread fallback path.
 */

function asNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

export function decodeSkillLeaderboardRows(
  payload: SkillLeaderboardIndex & { rowFields?: unknown },
): SkillLeaderboardIndex {
  const raw = payload as { rowFields?: unknown; rows?: unknown }
  const fields = Array.isArray(raw.rowFields) ? raw.rowFields.map(String) : []
  const rows: unknown[] = Array.isArray(raw.rows) ? raw.rows : []
  if (fields.length === 0 || rows.length === 0 || !Array.isArray(rows[0])) return payload
  const index = new Map(fields.map((field, position) => [field, position]))
  const pick = (row: readonly unknown[], field: string): unknown => {
    const position = index.get(field)
    return position === undefined ? undefined : row[position]
  }
  return {
    ...payload,
    rows: (rows as unknown[][]).map((row) => ({
      key: String(pick(row, 'key') ?? ''),
      name: String(pick(row, 'name') ?? ''),
      org: String(pick(row, 'org') ?? ''),
      score: Number(pick(row, 'score') ?? 0),
      topPercent: asNumber(pick(row, 'topPercent')),
      grade: (pick(row, 'grade') ?? null) as PanelGrade | null,
      uniqueProblems: Number(pick(row, 'uniqueProblems') ?? 0),
      coverage: Number(pick(row, 'coverage') ?? 0),
      rankScore: asNumber(pick(row, 'rankScore')) ?? undefined,
      effectiveProblems: Number(pick(row, 'effectiveProblems') ?? 0),
      evidenceLevel: (pick(row, 'evidenceLevel') as string | undefined) ?? 'legacy',
      confidence: asNumber(pick(row, 'confidence')) ?? 1,
    })) satisfies SkillLeaderboardIndexRow[],
  }
}
