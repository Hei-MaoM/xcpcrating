import { shardForKey } from './md5'

/** Compact row emitted by search/players/<prefix-hash>.json. */
export type PlayerSearchRow = [
  key: string,
  name: string,
  org: string,
  contests: number,
]

export interface PlayerSearchEntry {
  key: string
  name: string
  org: string
  contests: number
  hay: string
}

function normalized(value: string): string {
  return value.trim().toLowerCase()
}

/** Resolve the query's normalized first character to the exporter's md5 shard. */
export function playerSearchShard(query: string): string | null {
  const first = Array.from(normalized(query))[0]
  return first ? shardForKey(first) : null
}

export function decodePlayerSearchRows(
  rows: readonly PlayerSearchRow[],
): PlayerSearchEntry[] {
  return rows.map(([key, name, org, contests]) => ({
    key,
    name,
    org,
    contests,
    hay: `${name}\u0001${org}`.toLowerCase(),
  }))
}

/** Filter one prefix shard while stopping as soon as the UI result cap is met. */
export function filterPlayerSearchEntries(
  entries: readonly PlayerSearchEntry[],
  query: string,
  limit = 6,
): PlayerSearchEntry[] {
  const needle = normalized(query)
  if (!needle || limit <= 0) return []
  const matches: PlayerSearchEntry[] = []
  for (const entry of entries) {
    if (entry.hay.includes(needle)) {
      matches.push(entry)
      if (matches.length >= limit) break
    }
  }
  return matches
}
