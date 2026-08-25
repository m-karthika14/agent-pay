import { Route, Routes } from 'react-router-dom'
import { AppLayout } from '../layouts/AppLayout'
import { AuditPage } from '../pages/AuditPage'
import { MerchantConsolePage } from '../pages/MerchantConsolePage'
import { TransactionPage } from '../pages/TransactionPage'

/** Top-level route table -- the Merchant Console's three pages (plan.md Section 19.2). */
export function AppRoutes() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route path="/" element={<MerchantConsolePage />} />
        <Route path="/transactions/:transactionId" element={<TransactionPage />} />
        <Route path="/transactions/:transactionId/audit" element={<AuditPage />} />
      </Route>
    </Routes>
  )
}
