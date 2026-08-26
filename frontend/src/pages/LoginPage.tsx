import { useState } from 'react'
import type { FormEvent } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { useBuyer } from '../context/BuyerContext'

interface LocationState {
  from?: { pathname: string }
}

/**
 * Storefront login page (plan.md Section 19). Doubles as signup: an unknown
 * email creates an account, and a known email with no password yet (e.g.
 * one Claude/MCP already created via POST /api/users) claims whatever
 * password is typed here as its own -- see app.auth.service.login_or_claim.
 */
export function LoginPage() {
  const { login, loading, error } = useBuyer()
  const navigate = useNavigate()
  const location = useLocation()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [name, setName] = useState('')

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    try {
      await login(email, password, name || undefined)
      const state = location.state as LocationState | null
      navigate(state?.from?.pathname ?? '/', { replace: true })
    } catch {
      // error is already surfaced via useBuyer().error
    }
  }

  return (
    <div className="flex min-h-[70vh] items-center justify-center">
      <div className="w-full max-w-sm rounded-2xl border border-slate-200 bg-white p-8 shadow-sm">
        <p className="text-center text-sm font-semibold tracking-tight text-indigo-600">AgentPay</p>
        <h1 className="mt-1 text-center text-xl font-semibold text-slate-900">Welcome back 👋</h1>

        <form onSubmit={(e) => void handleSubmit(e)} className="mt-6 space-y-4">
          <label className="block text-sm">
            <span className="text-slate-600">Email</span>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none"
              placeholder="you@example.com"
              autoFocus
            />
          </label>

          <label className="block text-sm">
            <span className="text-slate-600">Password</span>
            <input
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none"
              placeholder="••••••••"
            />
          </label>

          <label className="block text-sm">
            <span className="text-slate-600">Name (only used the first time)</span>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none"
              placeholder="Optional"
            />
          </label>

          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-indigo-700 disabled:opacity-50"
          >
            {loading ? 'Logging in…' : 'Login'}
          </button>

          {error && <p className="text-sm text-red-600">{error.message}</p>}
        </form>

        <p className="mt-6 text-center text-xs text-slate-400">
          New here? Just enter an email and any password -- your account is created automatically.
        </p>
      </div>
    </div>
  )
}
