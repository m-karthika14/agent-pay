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
import { LandingPage } from '../pages/LandingPage'
import { LoginPage } from '../pages/LoginPage'
import { MerchantConsolePage } from '../pages/MerchantConsolePage'
import { OrderPage } from '../pages/OrderPage'
import { ProductPage } from '../pages/ProductPage'
import { TransactionPage } from '../pages/TransactionPage'

/**
 * Top-level route table. `/` is the merchant-picker landing page; every
 * merchant's storefront (product grid, detail, cart, checkout) lives under
 * `/store/:merchantSlug/...`, gated behind a real login (plan.md Section 19)
 * so the browser and Claude/MCP resolve to the same user_id. `/console`
 * onward is the read-only Merchant Console (plan.md Section 19.2), which
 * needs no buyer identity. `/agent` is the live "AI Activity" panel for
 * watching a buyer agent's checkout in real time.
 */
export function AppRoutes() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route path="/login" element={<LoginPage />} />

        <Route path="/" element={<LandingPage />} />
        <Route path="/store/:merchantSlug" element={<RequireBuyer><HomePage /></RequireBuyer>} />
        <Route path="/store/:merchantSlug/products/:productId" element={<RequireBuyer><ProductPage /></RequireBuyer>} />
        <Route path="/store/:merchantSlug/cart" element={<RequireBuyer><CartPage /></RequireBuyer>} />
        <Route path="/store/:merchantSlug/checkout" element={<RequireBuyer><CheckoutPage /></RequireBuyer>} />
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
