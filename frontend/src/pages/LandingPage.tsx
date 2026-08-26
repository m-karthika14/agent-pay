import { Link } from 'react-router-dom'
import { useMerchants } from '../hooks/useMerchants'
import { getMerchantTheme } from '../lib/merchantTheme'

const MERCHANT_ICON: Record<string, string> = {
  urbannest: '🏙️',
  techhub: '⚡',
}

/** AgentPay landing page: pick a merchant to shop directly, or hand your mandate_id to Claude, which can discover and compare across all of them. */
export function LandingPage() {
  const { data: merchants, loading, error } = useMerchants()

  return (
    <div className="mx-auto max-w-2xl space-y-8 py-8 text-center">
      <div className="space-y-2">
        <h1 className="text-2xl font-bold text-slate-900">AgentPay</h1>
        <p className="text-sm text-slate-500">
          Shop directly, or let your AI agent shop across every AI-transactable merchant below.
        </p>
      </div>

      {loading && <p className="text-sm text-slate-500">Loading merchants…</p>}
      {error && <p className="text-sm text-red-600">{error.message}</p>}

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
                <h2 className="text-lg font-semibold text-slate-900">{merchant.name}</h2>
                <p className="text-xs tracking-wide text-slate-400 uppercase">Electronics</p>
                <Link
                  to={`/store/${merchant.slug}`}
                  className={`mt-2 w-full rounded-md px-4 py-2 text-sm font-medium text-white transition ${theme.primaryButton}`}
                >
                  Shop
                </Link>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
