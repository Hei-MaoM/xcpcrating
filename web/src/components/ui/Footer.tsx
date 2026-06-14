import { Link } from 'react-router-dom'

/** Light Luxury footer — brand mark, provenance note, quick links. */
export function Footer() {
  return (
    <footer className="foot">
      <div className="foot__inner">
        <div>
          <div className="brand">
            <span className="brand__mark" style={{ fontSize: 18 }}>
              xcpc<span className="brand__dot"> · </span>rating
            </span>
          </div>
        </div>
        <div className="foot__links">
          <Link to="/">榜单</Link>
          <Link to="/contests">比赛</Link>
        </div>
      </div>
    </footer>
  )
}
