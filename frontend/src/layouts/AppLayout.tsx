import { Outlet } from 'react-router-dom'
import { GlobalAuthorizationPopup } from '../components/GlobalAuthorizationPopup'
import { GlobalLiveActivity } from '../components/GlobalLiveActivity'
import { Navbar } from '../components/Navbar'

/** Shared page chrome (nav bar + content container) wrapping every route (plan.md Section 19). GlobalAuthorizationPopup and GlobalLiveActivity sit here, not on any one page, so a pending Claude request -- and Claude's own live shopping activity -- surface regardless of which route the buyer is on (plan.md Phase 2). */
export function AppLayout() {
  return (
    <div className="min-h-screen bg-slate-50">
      <Navbar />
      <GlobalAuthorizationPopup />
      <GlobalLiveActivity />
      <main className="mx-auto max-w-5xl px-4 py-6">
        <Outlet />
      </main>
    </div>
  )
}
