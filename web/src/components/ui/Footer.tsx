import { Link } from 'react-router-dom'

/** Light Luxury footer — brand mark, repository link, quick links. */
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
          <a
            className="foot__repo"
            href="https://github.com/Hei-MaoM/xcpcrating"
            target="_blank"
            rel="noopener noreferrer"
          >
            github.com/Hei-MaoM/xcpcrating
          </a>
        </div>
        <div className="foot__links">
          <Link to="/">榜单</Link>
          <Link to="/contests">比赛</Link>
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
