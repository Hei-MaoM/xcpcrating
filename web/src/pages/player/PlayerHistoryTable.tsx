import { useMemo } from 'react'
import { Link } from 'react-router-dom'
import { DataTable, type Column } from '../../components/ui'
import type { PlayerHistoryEntry } from '../../lib/data'
import { formatDate, formatScore } from '../../lib/format'
import { sortedByTime } from './stats'

interface PlayerHistoryTableProps {
  history: PlayerHistoryEntry[]
}

function RankCell({ rank, teamCount }: { rank: number; teamCount: number }) {
  return (
    <span className="hist-rank">
      <span className="tnum">
        {rank}
        <span className="hist-rank__sep"> / </span>
        <span className="text-faint">{teamCount}</span>
      </span>
    </span>
  )
}

/**
 * Per-contest history table. Most-recent first. Contest names link to the
 * contest detail route (#/contest/<slug>; contestId is the slug). Podium ranks
 * are rendered the same as every other row (no medal styling). Columns:
 * 日期 / 比赛 / 队名 / 名次÷队数 / perf / C 赛后分 (the skill mean μ after the
 * contest; uncertainty is no longer surfaced).
 */
export function PlayerHistoryTable({ history }: PlayerHistoryTableProps) {
  // Newest first for a résumé-style read; sortedByTime returns ascending.
  const rows = useMemo(() => sortedByTime(history).reverse(), [history])

  const columns: Column<PlayerHistoryEntry>[] = [
    {
      key: 'date',
      header: '日期',
      width: '6.5rem',
      render: (h) => <span className="text-muted tnum">{formatDate(h.startAt)}</span>,
    },
    {
      key: 'contest',
      header: '比赛',
      render: (h) => (
        <Link className="link-contest" to={`/contest/${h.contestId}`}>
          {h.title}
        </Link>
      ),
    },
    {
      key: 'team',
      header: '队名',
      render: (h) => <span className="text-muted">{h.teamName || '—'}</span>,
    },
    {
      key: 'rank',
      header: '名次 / 队数',
      numeric: true,
      render: (h) => <RankCell rank={h.rank} teamCount={h.teamCount} />,
    },
    {
      key: 'perf',
      header: '表现分',
      numeric: true,
      render: (h) => <span className="hist-perf">{formatScore(h.perf)}</span>,
    },
    {
      key: 'rating',
      header: '赛后分',
      numeric: true,
      title: '本场结束后的阶梯分',
      render: (h) =>
        h.rating_after === null ? (
          <span className="text-faint">—</span>
        ) : (
          <span className="tnum">{formatScore(h.rating_after)}</span>
        ),
    },
  ]

  return (
    <DataTable
      columns={columns}
      rows={rows}
      rowKey={(h) => h.contestId}
      caption="选手逐场参赛历史"
      emptyMessage="暂无参赛记录"
    />
  )
}

export default PlayerHistoryTable
