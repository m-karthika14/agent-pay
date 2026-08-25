import { NavLink } from 'react-router-dom'

/** Top navigation bar for the Merchant Console (plan.md Section 19.2). */
export function Navbar() {
  return (
    <header className="border-b border-slate-200 bg-white">
      <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-3">
        <NavLink to="/" className="text-sm font-semibold tracking-tight text-slate-900">
          AgentPay Merchant Console
        </NavLink>
      </div>
    </header>
  )
}
