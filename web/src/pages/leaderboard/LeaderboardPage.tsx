import { useSearchParams } from 'react-router-dom'
import { PeriodBoard } from './PeriodBoard'
import { RatingsBoard } from './RatingsBoard'

/** Default caliber 正式参赛; ?board=all / ?board=period select the other views. */
type BoardKind = 'all' | 'official' | 'period'

function readBoard(raw: string | null): BoardKind {
  if (raw === 'all') return 'all'
  if (raw === 'period') return 'period'
  return 'official'
}

const BOARD_HINT: Record<BoardKind, string> = {
  official: '仅计入正式参赛，打星（非正式）场次不计。',
  all: '全部成绩计入积分，含打星（非正式）场次。',
  period: '截至选定日期、有过正式参赛的选手，分数为当时的历史评分。',
}

export default function LeaderboardPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const board = readBoard(searchParams.get('board'))

  // Switch board: persist in the URL and reset paging / period window so each
  // view opens clean (a stale page/from/to from another tab would mislead).
  function selectBoard(next: BoardKind) {
    setSearchParams(
      (prev) => {
        const merged = new URLSearchParams(prev)
        if (next === 'official') merged.delete('board')
        else merged.set('board', next)
        merged.delete('page')
        merged.delete('from') // legacy param from the earlier range-based view
        if (next !== 'period') merged.delete('to')
        return merged
      },
      { replace: false },
    )
  }

  return (
    <div className="page-enter">
      <section className="wrap phead">
        <span className="eyebrow eyebrow--oxford">积分榜单</span>
        <h1 className="display">选手榜单</h1>
      </section>

      <section className="wrap" style={{ paddingBottom: 64 }}>
        <div className="board-tabs">
          <div className="board-tabs__set" role="tablist" aria-label="榜单类型">
            <button
              type="button"
              role="tab"
              aria-selected={board === 'official'}
              className={`board-tab ${board === 'official' ? 'is-active' : ''}`}
              onClick={() => selectBoard('official')}
            >
              正式参赛
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={board === 'all'}
              className={`board-tab ${board === 'all' ? 'is-active' : ''}`}
              onClick={() => selectBoard('all')}
            >
              全部参赛
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={board === 'period'}
              className={`board-tab ${board === 'period' ? 'is-active' : ''}`}
              onClick={() => selectBoard('period')}
            >
              时间段
            </button>
          </div>
          <span className="board-tabs__hint">{BOARD_HINT[board]}</span>
        </div>

        {board === 'period' ? (
          <PeriodBoard />
        ) : (
          <RatingsBoard official={board === 'official'} />
        )}
      </section>
    </div>
  )
}
