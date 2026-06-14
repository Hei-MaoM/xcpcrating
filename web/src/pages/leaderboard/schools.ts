/*
 * Derivation helpers for the leaderboard's school (org) dropdown filter. Pure
 * and side-effect free so they can be unit-tested without a DOM. The board can
 * carry tens of thousands of rows across ~2k schools, so the option list is
 * built once per board load and narrowed client-side as the user types.
 */

/** One selectable school plus how many ranked players it has on the board. */
export interface SchoolOption {
  org: string
  count: number
}

/** Minimal row shape the builder needs — every board row carries `org`. */
interface OrgRow {
  org: string
}

/**
 * Collapse board rows into a distinct, sorted school list. Rows with an empty
 * or whitespace-only org are skipped (defensive — the current export has none).
 * Ordering is by player count descending, then school name ascending so the
 * most-represented schools surface first and ties stay deterministic. Chinese
 * and English names are both present, so name ties use a zh-CN collator.
 */
export function buildSchoolOptions(
  rows: ReadonlyArray<OrgRow>,
): SchoolOption[] {
  const counts = new Map<string, number>()
  for (const row of rows) {
    const org = row.org?.trim()
    if (!org) continue
    counts.set(org, (counts.get(org) ?? 0) + 1)
  }

  return Array.from(counts, ([org, count]) => ({ org, count })).sort(
    (a, b) => b.count - a.count || a.org.localeCompare(b.org, 'zh-CN'),
  )
}

/**
 * Narrow the option list by a case-insensitive substring match on the school
 * name. An empty query returns a copy of the full list (order preserved). Used
 * only to filter which options render in the dropdown — it never touches the
 * board data itself.
 */
export function filterSchoolOptions(
  options: ReadonlyArray<SchoolOption>,
  query: string,
): SchoolOption[] {
  const q = query.trim().toLowerCase()
  if (!q) return [...options]
  return options.filter((option) => option.org.toLowerCase().includes(q))
}
