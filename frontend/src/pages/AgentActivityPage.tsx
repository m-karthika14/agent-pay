import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { ActivityTimeline } from '../components/ActivityTimeline'
import { StatusBadge } from '../components/StatusBadge'
import { usePolling } from '../hooks/usePolling'
import { getMandateAuditEvents } from '../services/auditApi'
import { getCartByMandate } from '../services/cartApi'
import { getMandate } from '../services/mandateApi'
import { formatCurrency } from '../lib/formatCurrency'

/**
 * Live "AI Activity" panel (plan.md storefront spec): paste a mandate_id --
 * the one handed to Claude in conversation to authorize a purchase -- and
 * watch AgentPay's checkout boundary run in near-real-time via polling.
 * Claude creates its own cart through MCP independent of any browser
 * session, so this page has no other way to know which mandate to watch.
 */
export function AgentActivityPage() {
  const [searchParams] = useSearchParams()
  const [input, setInput] = useState(searchParams.get('mandate') ?? '')
  const [watching, setWatching] = useState<string | null>(searchParams.get('mandate'))

  const mandate = usePolling(() => getMandate(watching as string), [watching], {
    enabled: watching !== null,
    intervalMs: 2000,
  })
  const cart = usePolling(() => getCartByMandate(watching as string), [watching], {
    enabled: watching !== null,
    intervalMs: 2000,
  })
  const activity = usePolling(() => getMandateAuditEvents(watching as string), [watching], {
    enabled: watching !== null,
    intervalMs: 2000,
  })

  return (
    <div className="max-w-2xl space-y-6">
      <div>
        <h1 className="text-lg font-semibold text-slate-900">AI Activity</h1>
        <p className="text-sm text-slate-500">
          Watch a buyer agent (e.g. Claude, via MCP) shop UrbanNest in near-real-time.
        </p>
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault()
          setWatching(input.trim() || null)
        }}
        className="flex gap-2"
      >
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Paste a mandate_id, e.g. M-a1b2c3d4"
          className="flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm font-mono"
        />
        <button type="submit" className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white">
          Watch
        </button>
      </form>

      {watching && (
        <div className="space-y-4">
          {mandate.error && <p className="text-sm text-red-600">{mandate.error.message}</p>}

          {mandate.data && (
            <div className="rounded-lg border border-slate-200 bg-white p-4">
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-semibold text-slate-700">Mandate {mandate.data.mandate_id}</h2>
                <StatusBadge status={mandate.data.status} />
              </div>
              <dl className="mt-2 grid grid-cols-2 gap-2 text-xs text-slate-500">
                <div>
                  <dt>Product type</dt>
                  <dd className="text-slate-800">{mandate.data.product_type}</dd>
                </div>
                <div>
                  <dt>Spending cap</dt>
                  <dd className="text-slate-800">{formatCurrency(mandate.data.max_amount_minor, mandate.data.currency)}</dd>
                </div>
                <div>
                  <dt>Allowed categories</dt>
                  <dd className="text-slate-800">{mandate.data.allowed_categories.join(', ')}</dd>
                </div>
                <div>
                  <dt>Expires</dt>
                  <dd className="text-slate-800">{new Date(mandate.data.expires_at).toLocaleString()}</dd>
                </div>
              </dl>
            </div>
          )}

          {cart.data && (() => {
            const cartData = cart.data
            return (
              <div className="rounded-lg border border-slate-200 bg-white p-4">
                <h2 className="mb-2 text-sm font-semibold text-slate-700">Cart</h2>
                <ul className="divide-y divide-slate-100 text-sm">
                  {cartData.items.map((item) => (
                    <li key={item.item_id} className="flex items-center justify-between py-1.5">
                      <span>
                        {item.product_name} × {item.quantity}
                      </span>
                      <span className="font-medium text-slate-900">
                        {formatCurrency(item.line_total_minor, cartData.currency)}
                      </span>
                    </li>
                  ))}
                </ul>
                <div className="mt-2 flex items-center justify-between border-t border-slate-100 pt-2 text-sm font-semibold">
                  <span>Subtotal</span>
                  <span>{formatCurrency(cartData.subtotal_minor, cartData.currency)}</span>
                </div>
              </div>
            )
          })()}

          <div className="rounded-lg border border-slate-200 bg-white p-4">
            <h2 className="mb-3 text-sm font-semibold text-slate-700">Activity</h2>
            {activity.loading && !activity.data && <p className="text-sm text-slate-500">Loading…</p>}
            {activity.data && activity.data.length === 0 && (
              <p className="text-sm text-slate-500">No activity recorded yet for this mandate.</p>
            )}
            {activity.data && activity.data.length > 0 && <ActivityTimeline events={activity.data} />}
          </div>
        </div>
      )}
    </div>
  )
}
