import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

/** Shape of the /stats.json the origin publishes (see tmp/xcpcrating-stats.py). */
type VisitStats = {
  total_pv: number
  total_uv: number
  today_pv: number
  today_uv: number
  updated?: string
}

/**
 * Fetch the visit counter, and keep it fresh.
 *
 * The file is rewritten on the origin every few minutes from the nginx access log.  A
 * single fetch on mount would leave a visitor staring at a stale number, so refresh on an
 * interval too — but only while the tab is actually visible, since a background tab
 * polling an origin is pure waste.
 */
function useVisitStats(): VisitStats | null {
  const [stats, setStats] = useState<VisitStats | null>(null)

  useEffect(() => {
    let alive = true

    const load = () => {
      fetch('./stats.json', { cache: 'no-cache' })
        .then((response) => (response.ok ? response.json() : null))
        .then((data: VisitStats | null) => {
          if (alive && data && typeof data.total_uv === 'number') setStats(data)
        })
        .catch(() => {
          /* 统计文件不存在或被拦截：静默隐藏即可 */
        })
    }

    load()
    // 源站汇总每 5 分钟一次，所以 2 分钟刷一次足够及时，也不会造成明显请求量
    const timer = window.setInterval(() => {
      if (document.visibilityState === 'visible') load()
    }, 120000)

    return () => {
      alive = false
      window.clearInterval(timer)
    }
  }, [])

  return stats
}

/** 五位数以上折算成「万」，避免页脚出现一串数字把排版撑开。 */
function formatCount(value: number): string {
  if (value >= 10000) return `${(value / 10000).toFixed(1)} 万`
  return value.toLocaleString('zh-CN')
}

/** Light Luxury footer — brand mark, repository link, quick links, visit counter. */
export function Footer() {
  const stats = useVisitStats()

  return (
    <footer className="foot">
      <div className="foot__inner">
        <div>
          <div className="brand">
            <span className="brand__mark" style={{ fontSize: 18 }}>
              xcpc<span className="brand__dot"> · </span>rating
            </span>
          </div>
          <a
            className="foot__repo"
            href="https://github.com/Hei-MaoM/xcpcrating"
            target="_blank"
            rel="noopener noreferrer"
          >
            github.com/Hei-MaoM/xcpcrating
          </a>
          {stats ? (
            <div
              className="foot__stats"
              title={
                `今日访客 ${stats.today_uv} 人 / ${stats.today_pv} 次浏览\n` +
                `累计访客 ${stats.total_uv} 人次 / ${stats.total_pv} 次浏览\n` +
                `按天去重后相加，非跨日去重；每日更新一次` +
                (stats.updated ? `\n更新于 ${stats.updated}` : '')
              }
            >
              今日 <b>{formatCount(stats.today_uv)}</b> 人 · 累计{' '}
              <b>{formatCount(stats.total_uv)}</b> 人次
            </div>
          ) : null}
        </div>
        <div className="foot__links">
          <Link to="/">榜单</Link>
          <Link to="/contests">比赛</Link>
          <Link to="/setters">出题组</Link>
          <Link to="/rules">规则</Link>
          <a
            href="https://github.com/Hei-MaoM/xcpcrating"
            target="_blank"
            rel="noopener noreferrer"
          >
            GitHub
          </a>
        </div>
      </div>
    </footer>
  )
}
