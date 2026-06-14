import { HashRouter, Routes, Route, Navigate } from 'react-router-dom'
import { TopBar, Footer } from './components/ui'
import LeaderboardPage from './pages/leaderboard/LeaderboardPage'
import ContestsPage from './pages/contests/ContestsPage'
import ContestDetailPage from './pages/contests/ContestDetailPage'
import PlayerPage from './pages/player/PlayerPage'
import RulesPage from './pages/rules/RulesPage'

/**
 * Application shell + route table. HashRouter keeps deploys configuration-free
 * on GitHub Pages. TopBar and Footer frame every page (Light Luxury design);
 * the sticky footer is pinned to the bottom by the flex .app-shell column.
 */
export default function App() {
  return (
    <HashRouter>
      <div className="app-shell">
        <a className="skip-link" href="#main">
          跳到主内容
        </a>
        <TopBar />
        <main id="main" className="app-main">
          <Routes>
            <Route path="/" element={<LeaderboardPage />} />
            <Route path="/contests" element={<ContestsPage />} />
            <Route path="/contest/:slug" element={<ContestDetailPage />} />
            <Route path="/player/:key" element={<PlayerPage />} />
            <Route path="/rules" element={<RulesPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
        <Footer />
      </div>
    </HashRouter>
  )
}
