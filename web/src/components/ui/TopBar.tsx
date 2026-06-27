import { NavLink } from 'react-router-dom'
import { SearchBox } from './SearchBox'

/** Sticky Light Luxury top bar: brand mark, nav, global search. */
export function TopBar() {
  return (
    <header className="topbar">
      <div className="topbar__inner">
        <NavLink to="/" className="brand" aria-label="xcpc rating 首页">
          <span className="brand__mark">
            xcpc<span className="brand__dot"> · </span>rating
          </span>
        </NavLink>

        <nav className="nav" aria-label="主导航">
          <NavLink to="/" end className={({ isActive }) => (isActive ? 'is-active' : '')}>
            榜单
          </NavLink>
          <NavLink to="/schools" className={({ isActive }) => (isActive ? 'is-active' : '')}>
            学校
          </NavLink>
          <NavLink to="/contests" className={({ isActive }) => (isActive ? 'is-active' : '')}>
            比赛
          </NavLink>
          <NavLink to="/rules" className={({ isActive }) => (isActive ? 'is-active' : '')}>
            规则
          </NavLink>
        </nav>

        <SearchBox />
      </div>
    </header>
  )
}
