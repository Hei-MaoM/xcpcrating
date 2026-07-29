import { NavLink } from 'react-router-dom'

/** Local navigation shared by the contest archive and metric views. */
export function ContestSectionNav() {
  return (
    <nav className="contest-subnav" aria-label="比赛页面">
      <NavLink
        to="/contests"
        end
        className={({ isActive }) => (isActive ? 'is-active' : '')}
      >
        比赛列表
      </NavLink>
      <NavLink
        to="/contests/rankings"
        className={({ isActive }) => (isActive ? 'is-active' : '')}
      >
        赛事榜
      </NavLink>
      <NavLink
        to="/contests/trends"
        className={({ isActive }) => (isActive ? 'is-active' : '')}
      >
        赛季比较
      </NavLink>
    </nav>
  )
}
