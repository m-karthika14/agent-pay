import { Outlet } from 'react-router-dom'
import { Navbar } from '../components/Navbar'

/** Shared page chrome (nav bar + content container) wrapping every route (plan.md Section 19). */
export function AppLayout() {
  return (
    <div className="min-h-screen bg-slate-50">
      <Navbar />
      <main className="mx-auto max-w-5xl px-4 py-6">
        <Outlet />
      </main>
    </div>
  )
}
