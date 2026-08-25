import { BrowserRouter } from 'react-router-dom'
import { AppRoutes } from './routes/AppRoutes'

/**
 * Root application composition for AgentPay.
 *
 * Phase 11 (plan.md Section 19.2): wires React Router around the Merchant
 * Console's three pages. The buyer-facing storefront (HomePage,
 * ProductPage, CartPage, CheckoutPage) is not part of this phase --
 * plan.md Section 18 treats the MCP/API as the real buyer interface, not a
 * human-facing storefront.
 */
function App() {
  return (
    <BrowserRouter>
      <AppRoutes />
    </BrowserRouter>
  )
}

export default App
