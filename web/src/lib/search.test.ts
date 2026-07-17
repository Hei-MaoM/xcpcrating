import { describe, expect, it } from 'vitest'
import {
  decodePlayerSearchRows,
  filterPlayerSearchEntries,
  playerSearchShard,
  type PlayerSearchRow,
} from './search'

describe('player search prefix shards', () => {
  const rows: PlayerSearchRow[] = [
    ['alice@pku', 'Alice', '北京大学', 5],
    ['amy@thu', 'Amy', '清华大学', 3],
  ]

  it('derives a stable shard from the normalized first query character', () => {
    expect(playerSearchShard('  ALICE ')).toBe(playerSearchShard('alice'))
    expect(playerSearchShard('北京')).toBe(playerSearchShard('北'))
    expect(playerSearchShard('   ')).toBeNull()
  })

  it('decodes compact rows and filters within the loaded prefix shard', () => {
    const entries = decodePlayerSearchRows(rows)
    expect(filterPlayerSearchEntries(entries, 'ali').map((row) => row.key)).toEqual([
      'alice@pku',
    ])
    expect(filterPlayerSearchEntries(entries, '北京').map((row) => row.key)).toEqual([
      'alice@pku',
    ])
  })

  it('caps results without scanning beyond the requested result budget', () => {
    const entries = decodePlayerSearchRows(rows)
    expect(filterPlayerSearchEntries(entries, 'a', 1)).toHaveLength(1)
  })
})
