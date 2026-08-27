import { Link } from 'react-router-dom'
import { BudgetSettings } from '../components/BudgetSettings'
import { useBuyer } from '../context/BuyerContext'
import { useMerchants } from '../hooks/useMerchants'
import { getMerchantTheme } from '../lib/merchantTheme'

const MERCHANT_ICON: Record<string, string> = {
  urbannest: '🏙️',
  techhub: '⚡',
}

const HOW_IT_WORKS = [
  {
    title: 'Set a spending limit',
    body: 'Category, budget, and how long it lasts — the one thing that actually authorizes a purchase.',
  },
  {
    title: 'Shop, or hand it to Claude',
    body: 'Browse a store yourself, or let an AI buyer agent search, compare merchants, and build a cart on your behalf.',
  },
  {
    title: 'Claude asks, you decide',
    body: 'A real approval request appears right here — Reject, Edit the terms, or Approve. Never just a chat message.',
  },
  {
    title: "AgentPay checks every step",
    body: 'A merchant can propose an add-on, but it only goes through if it fits what you actually authorized.',
  },
  {
    title: 'Pay, once everything checks out',
    body: 'Payment only happens after every deterministic check passes — never before.',
  },
]

/** AgentPay's dashboard: an introduction to the product, the "how it works" flow, a login CTA, and the store picker (shopping itself is gated behind login). */
export function LandingPage() {
  const { userId, name, logout } = useBuyer()
  const { data: merchants, loading, error } = useMerchants()

  return (
    <div className="mx-auto max-w-4xl space-y-14 py-8">
      <section className="space-y-4 text-center">
        <h1 className="text-3xl font-bold text-slate-900">AgentPay</h1>
        <p className="mx-auto max-w-xl text-sm text-slate-500">
          A payments boundary for AI buyer agents. Shop directly, or let Claude shop for you — every purchase is
          bounded by a spending mandate you set, checked deterministically before a rupee moves.
        </p>
        {userId ? (
          <div className="space-y-3">
            <div className="flex items-center justify-center gap-3 text-sm">
              <span className="text-slate-600">
                Logged in as <span className="font-medium text-slate-900">{name}</span>
              </span>
              <button type="button" onClick={logout} className="font-medium text-slate-500 underline hover:text-slate-700">
                Log out
              </button>
            </div>
            <BudgetSettings userId={userId} />
          </div>
        ) : (
          <Link
            to="/login"
            className="inline-block rounded-md bg-slate-900 px-5 py-2.5 text-sm font-medium text-white transition hover:bg-slate-800"
          >
            Login
          </Link>
        )}
      </section>

      <section>
        <h2 className="mb-5 text-center text-sm font-semibold tracking-wide text-slate-400 uppercase">How it works</h2>
        <ol className="mx-auto max-w-xl space-y-4">
          {HOW_IT_WORKS.map((step, i) => (
            <li key={step.title} className="flex gap-4">
              <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border-2 border-slate-300 text-xs font-semibold text-slate-500">
                {i + 1}
              </span>
              <div>
                <p className="text-sm font-semibold text-slate-800">{step.title}</p>
                <p className="text-sm text-slate-500">{step.body}</p>
              </div>
            </li>
          ))}
        </ol>
      </section>

      <section>
        <h2 className="mb-5 text-center text-sm font-semibold tracking-wide text-slate-400 uppercase">Stores</h2>

        {loading && <p className="text-center text-sm text-slate-500">Loading merchants…</p>}
        {error && <p className="text-center text-sm text-red-600">{error.message}</p>}

        {merchants && (
          <div className="grid gap-4 sm:grid-cols-2">
            {merchants.map((merchant) => {
              const theme = getMerchantTheme(merchant.slug)
              return (
                <div
                  key={merchant.merchant_id}
                  className="flex flex-col items-center gap-3 rounded-2xl border border-slate-200 bg-white p-8 text-center"
                >
                  <span className="text-4xl" aria-hidden="true">
                    {MERCHANT_ICON[merchant.slug] ?? '🏪'}
                  </span>
                  <h3 className="text-lg font-semibold text-slate-900">{merchant.name}</h3>
                  <p className="text-xs tracking-wide text-slate-400 uppercase">Electronics</p>
                  {userId ? (
                    <Link
                      to={`/store/${merchant.slug}`}
                      className={`mt-2 w-full rounded-md px-4 py-2 text-sm font-medium text-white transition ${theme.primaryButton}`}
                    >
                      Shop
                    </Link>
                  ) : (
                    <p className="mt-2 text-xs text-slate-400">Log in to shop</p>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </section>
    </div>
  )
}
