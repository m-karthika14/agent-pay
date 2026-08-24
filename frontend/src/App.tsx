/**
 * Root application composition for AgentPay.
 *
 * This is a Phase 0 placeholder: it only confirms the Vite + React + Tailwind
 * toolchain is wired correctly. Real routing (React Router) and pages
 * (HomePage, ProductPage, CheckoutPage, MerchantConsolePage, ...) are added
 * in Phase 2 / Phase 19 per plan.md Section 19 (Frontend Implementation).
 */
function App() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-white text-slate-900">
      <div className="text-center">
        <h1 className="text-3xl font-semibold">AgentPay</h1>
        <p className="mt-2 text-slate-500">
          Merchant-side authorization gateway — scaffold ready.
        </p>
      </div>
    </main>
  )
}

export default App
