import type { ReactNode } from 'react'
import type { Column } from '../../components/ui'
import type { LeaderboardRow } from '../../lib/data'
import { formatScore } from '../../lib/format'

/**
 * A leaderboard row carries a stable 1-based overall rank (its position in the
 * full, unfiltered board) so the rank column reflects the player's true
 * standing even when an org filter is applied or the user is on page 2+.
 */
export interface RankedRow {
  rank: number
}

/** The single leaderboard row (incremental ladder) plus its overall rank. */
export type LeaderboardEntry = LeaderboardRow & RankedRow

/** Serif rank numeral. */
function rankCell(rank: number): ReactNode {
  return <span className="rank-numeral lb-rank">{rank}</span>
}

/** Player name; the row itself is the link target, so this stays plain text. */
function nameCell(name: string): ReactNode {
  return <span className="lb-name">{name}</span>
}

/**
 * School cell. Clicking filters the board to the same school without bubbling
 * the row's navigate-to-player click.
 */
function orgCell(org: string, onFilterOrg: (org: string) => void): ReactNode {
  if (!org) return <span className="text-faint">—</span>
  return (
    <button
      type="button"
      className="lb-org"
      onClick={(event) => {
        event.stopPropagation()
        onFilterOrg(org)
      }}
      title={`筛选 ${org} 的选手`}
    >
      {org}
    </button>
  )
}

interface ColumnDeps {
  onFilterOrg: (org: string) => void
}

/**
 * Build the leaderboard column set: 名次 / 选手 / 学校 / 分数 / 场次.
 * The score column is the incremental ladder score (climbed from 0).
 */
export function buildColumns({ onFilterOrg }: ColumnDeps): Column<LeaderboardEntry>[] {
  return [
    {
      key: 'rank',
      header: '名次',
      width: '4.5rem',
      render: (row) => rankCell(row.rank),
    },
    {
      key: 'name',
      header: '选手',
      render: (row) => nameCell(row.name),
    },
    {
      key: 'org',
      header: '学校',
      render: (row) => orgCell(row.org, onFilterOrg),
    },
    {
      key: 'rating',
      header: '分数',
      title: '阶梯分：从 0 起步，逐场累积',
      numeric: true,
      width: '6rem',
      render: (row) => <span className="lb-rating">{formatScore(row.rating)}</span>,
    },
    {
      key: 'contests',
      header: '场次',
      numeric: true,
      width: '4.5rem',
      render: (row) => row.contests,
    },
  ]
}
