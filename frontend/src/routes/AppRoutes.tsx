import { Route, Routes } from 'react-router-dom'
import { AppLayout } from '../layouts/AppLayout'
import { RequireBuyer } from '../components/RequireBuyer'
import { AgentActivityPage } from '../pages/AgentActivityPage'
import { AuditPage } from '../pages/AuditPage'
import { AuthorizeAgentPage } from '../pages/AuthorizeAgentPage'
import { CartPage } from '../pages/CartPage'
import { CheckoutPage } from '../pages/CheckoutPage'
import { HistoryPage } from '../pages/HistoryPage'
import { HomePage } from '../pages/HomePage'
import { LoginPage } from '../pages/LoginPage'
import { MerchantConsolePage } from '../pages/MerchantConsolePage'
import { OrderPage } from '../pages/OrderPage'
import { ProductPage } from '../pages/ProductPage'
import { TransactionPage } from '../pages/TransactionPage'

/**
 * Top-level route table. `/` onward is the UrbanNest storefront (the
 * merchant Claude/MCP also transacts against), gated behind a real login
 * (plan.md Section 19) so the browser and Claude/MCP resolve to the same
 * user_id; `/console` onward is the read-only Merchant Console (plan.md
 * Section 19.2), which needs no buyer identity. `/agent` is the live
 * "AI Activity" panel for watching a buyer agent's checkout in real time.
 */
export function AppRoutes() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route path="/login" element={<LoginPage />} />

        <Route path="/" element={<RequireBuyer><HomePage /></RequireBuyer>} />
        <Route path="/products/:productId" element={<RequireBuyer><ProductPage /></RequireBuyer>} />
        <Route path="/cart" element={<RequireBuyer><CartPage /></RequireBuyer>} />
        <Route path="/checkout" element={<RequireBuyer><CheckoutPage /></RequireBuyer>} />
        <Route path="/order/:orderId" element={<RequireBuyer><OrderPage /></RequireBuyer>} />
        <Route path="/history" element={<RequireBuyer><HistoryPage /></RequireBuyer>} />
        <Route path="/authorize-agent" element={<RequireBuyer><AuthorizeAgentPage /></RequireBuyer>} />
        <Route path="/agent" element={<AgentActivityPage />} />

        <Route path="/console" element={<MerchantConsolePage />} />
        <Route path="/console/transactions/:transactionId" element={<TransactionPage />} />
        <Route path="/console/transactions/:transactionId/audit" element={<AuditPage />} />
      </Route>
    </Routes>
  )
}
