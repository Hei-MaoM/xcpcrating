import { lazy, Suspense } from 'react'
import { HashRouter, Routes, Route, Navigate } from 'react-router-dom'
import { TopBar, Footer } from './components/ui'
import LeaderboardPage from './pages/leaderboard/LeaderboardPage'

const SchoolsPage = lazy(() => import('./pages/schools/SchoolsPage'))
const SchoolPage = lazy(() => import('./pages/schools/SchoolPage'))
const ContestsPage = lazy(() => import('./pages/contests/ContestsPage'))
const ContestDetailPage = lazy(
  () => import('./pages/contests/ContestDetailPage'),
)
const PredictionsPage = lazy(() => import('./pages/predictions/PredictionsPage'))
const PredictionPage = lazy(() => import('./pages/predictions/PredictionPage'))
// PlayerPage owns ECharts, so route splitting keeps the chart runtime entirely
// out of the leaderboard's critical JavaScript chunk.
const PlayerPage = lazy(() => import('./pages/player/PlayerPage'))
const RulesPage = lazy(() => import('./pages/rules/RulesPage'))

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
          <Suspense
            fallback={
              <div className="state" role="status">
                页面加载中…
              </div>
            }
          >
            <Routes>
              <Route path="/" element={<LeaderboardPage />} />
              <Route path="/schools" element={<SchoolsPage />} />
              <Route path="/school/:org" element={<SchoolPage />} />
              <Route path="/contests" element={<ContestsPage />} />
              <Route path="/contest/:slug" element={<ContestDetailPage />} />
              <Route path="/predictions" element={<PredictionsPage />} />
              <Route path="/prediction/:slug" element={<PredictionPage />} />
              <Route path="/player/:key" element={<PlayerPage />} />
              <Route path="/rules" element={<RulesPage />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </Suspense>
        </main>
        <Footer />
      </div>
    </HashRouter>
  )
}
