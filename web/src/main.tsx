import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
// Style import order matters: tokens -> typography -> global -> ui kit.
import './styles/tokens.css'
import './styles/typography.css'
import './styles/global.css'
import './components/ui/ui.css'
import App from './App'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
