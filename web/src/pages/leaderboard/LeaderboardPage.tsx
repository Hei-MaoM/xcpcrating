import { useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import { SKILL_AXIS_ORDER } from '../../lib/data'
import { PeriodBoard } from './PeriodBoard'
import { RatingsBoard } from './RatingsBoard'
import { SkillBoard } from './SkillBoard'
import { warmSkillBoard } from './skillBoardWorker'

/** Default caliber 正式参赛; ?board=all / ?board=period / ?board=skill pick the other views. */
type BoardKind = 'all' | 'official' | 'period' | 'skill'

function readBoard(raw: string | null): BoardKind {
  if (raw === 'all') return 'all'
  if (raw === 'period') return 'period'
  if (raw === 'skill') return 'skill'
  return 'official'
}

/** 低于这个吞吐就不预取那 6 MB（KB/s）—— 约等于 3 Mbps 出头。 */
const PREFETCH_MIN_KBPS = 400

/**
 * 实测链路吞吐（KB/s），测不出来就返回 0。
 *
 * 为什么不用 `navigator.connection.downlink` / `effectiveType`：它们报的是"本机到路由器"
 * 的那一段，在代理、VPN、或者运营商限速的链路后面经常显示成 4g，完全反映不了真实速度。
 * （实测：某条走了美国 LA 绕行的链路上，`effectiveType` 是 4g，而 328 KB 的文件花了 6 秒，
 * 折合 54 KB/s。）
 *
 * 所以拿已经真实发生过的同源请求来算：用 encodedBodySize（压缩后字节数）除以
 * 传输耗时，并扣掉一个往返延迟——小文件的耗时几乎全是延迟，不减掉会把吞吐算得极低。
 * 只挑够大的请求来量，太小的样本噪声太大。
 */
function measureThroughputKbps(): number {
  if (typeof performance === 'undefined' || !performance.getEntriesByType) return 0
  const entries = performance.getEntriesByType('resource') as PerformanceResourceTiming[]
  let best = 0
  for (const entry of entries) {
    const bytes = entry.encodedBodySize || entry.transferSize || 0
    if (bytes < 32768) continue          // 小于 32 KB 的样本，延迟占主导，测不准
    const roundTrip = entry.responseStart - entry.requestStart
    const transferMs = entry.duration - Math.max(roundTrip, 0)
    if (transferMs < 20) continue        // 快到测不出——那本来就是快链路
    best = Math.max(best, bytes / (transferMs / 1000) / 1024)
  }
  return best
}

/**
 * Warm the biggest asset the site has (one ~6 MB axis board) once the browser
 * is idle, so opening the 维度榜单 tab renders immediately.
 *
 * 这个预取很容易帮倒忙：它要拉 6 MB，而首屏真正需要的数据只有几十 KB。
 * 在慢链路上它会和首屏抢带宽，把页面拖成"打不开"。所以只有**实测链路够快**时才预取；
 * 测不出来时保守地不预取——不预取的代价只是点开维度榜单时多等一次，
 * 比把首屏拖死小得多。
 */
function useSkillBoardPrefetch(): void {
  useEffect(() => {
    const connection = (navigator as Navigator & {
      connection?: { saveData?: boolean; effectiveType?: string }
    }).connection
    if (connection?.saveData) return
    if (connection?.effectiveType && /(^|-)2g$/.test(connection.effectiveType)) return

    const warm = () => {
      if (measureThroughputKbps() < PREFETCH_MIN_KBPS) return
      warmSkillBoard('official', 'overall', SKILL_AXIS_ORDER[0])
    }

    const idle = (window as Window & { requestIdleCallback?: (cb: () => void, options?: { timeout: number }) => number }).requestIdleCallback
    if (idle) {
      // timeout 给 8 秒：留足时间让首屏那几个请求先跑完，好让上面的测量有样本可依
      const handle = idle(warm, { timeout: 8000 })
      return () => {
        (window as Window & { cancelIdleCallback?: (handle: number) => void }).cancelIdleCallback?.(handle)
      }
    }
    const timer = window.setTimeout(warm, 4000)
    return () => window.clearTimeout(timer)
  }, [])
}

const BOARD_HINT: Record<BoardKind, string> = {
  official: '仅计入正式参赛，打星（非正式）场次不计。',
  all: '全部成绩计入积分，含打星（非正式）场次。',
  period: '截至选定日期、有过正式参赛的选手，分数为当时的历史评分。',
  skill: '按核心解法把题目归入十三个维度，比较选手在不同维度上的长期能力。',
}

export default function LeaderboardPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const board = readBoard(searchParams.get('board'))
  useSkillBoardPrefetch()

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
        // The thirteen-dimension board owns these; drop them when it is closed so
        // the other boards never inherit a stale axis or search term.
        if (next !== 'skill') {
          merged.delete('axis')
          merged.delete('caliber')
          merged.delete('q')
        }
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
            <button
              type="button"
              role="tab"
              aria-selected={board === 'skill'}
              className={`board-tab ${board === 'skill' ? 'is-active' : ''}`}
              onClick={() => selectBoard('skill')}
            >
              维度榜单
            </button>
          </div>
          {board !== 'skill' && <span className="board-tabs__hint">{BOARD_HINT[board]}</span>}
        </div>

        {board === 'period' ? (
          <PeriodBoard />
        ) : board === 'skill' ? (
          <SkillBoard />
        ) : (
          <RatingsBoard official={board === 'official'} />
        )}
      </section>
    </div>
  )
}
