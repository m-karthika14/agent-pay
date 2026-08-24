import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'

/**
 * Mounts the AgentPay React app into the DOM. Global providers (routing,
 * shared context) are added here as they're introduced in later phases —
 * see plan.md Section 44 for main.tsx's responsibilities.
 */
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
