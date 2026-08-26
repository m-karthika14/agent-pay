import { Route, Routes } from 'react-router-dom'
import { AppLayout } from '../layouts/AppLayout'
import { AgentActivityPage } from '../pages/AgentActivityPage'
import { AuditPage } from '../pages/AuditPage'
import { CartPage } from '../pages/CartPage'
import { CheckoutPage } from '../pages/CheckoutPage'
import { HistoryPage } from '../pages/HistoryPage'
import { HomePage } from '../pages/HomePage'
import { MerchantConsolePage } from '../pages/MerchantConsolePage'
import { OrderPage } from '../pages/OrderPage'
import { ProductPage } from '../pages/ProductPage'
import { TransactionPage } from '../pages/TransactionPage'

/**
 * Top-level route table. `/` onward is the UrbanNest storefront (the
 * merchant Claude/MCP also transacts against); `/console` onward is the
 * read-only Merchant Console (plan.md Section 19.2). `/agent` is the live
 * "AI Activity" panel for watching a buyer agent's checkout in real time.
 */
export function AppRoutes() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route path="/" element={<HomePage />} />
        <Route path="/products/:productId" element={<ProductPage />} />
        <Route path="/cart" element={<CartPage />} />
        <Route path="/checkout" element={<CheckoutPage />} />
        <Route path="/order/:orderId" element={<OrderPage />} />
        <Route path="/history" element={<HistoryPage />} />
        <Route path="/agent" element={<AgentActivityPage />} />

        <Route path="/console" element={<MerchantConsolePage />} />
        <Route path="/console/transactions/:transactionId" element={<TransactionPage />} />
        <Route path="/console/transactions/:transactionId/audit" element={<AuditPage />} />
      </Route>
    </Routes>
  )
}
