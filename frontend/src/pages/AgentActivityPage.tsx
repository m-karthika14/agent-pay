import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { LiveConversation } from '../components/LiveConversation'
import { StatusBadge } from '../components/StatusBadge'
import { useBuyer } from '../context/BuyerContext'
import { useMerchants } from '../hooks/useMerchants'
import { usePolling } from '../hooks/usePolling'
import { getMandateAuditEvents } from '../services/auditApi'
import { getCartByMandate } from '../services/cartApi'
import { getMandate, listMandatesForUser } from '../services/mandateApi'
import { formatCurrency } from '../lib/formatCurrency'
import { getMerchantTheme } from '../lib/merchantTheme'
import type { MerchantResponse } from '../types/merchant'

const DAY_MS = 24 * 60 * 60 * 1000

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.round(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hours = Math.round(mins / 60)
  return `${hours}h ago`
}

/**
 * Live "AI Activity" panel (plan.md storefront spec): watch AgentPay's
 * checkout boundary run in near-real-time as a buyer agent shops via MCP.
 * Logged-in buyers get a list of the mandates they authorized in the last
 * 24 hours -- click one to open its live detail. A mandate_id can also be
 * pasted directly (e.g. one handed to Claude in another session).
 */
export function AgentActivityPage() {
  const [searchParams] = useSearchParams()
  const { userId } = useBuyer()
  const [input, setInput] = useState(searchParams.get('mandate') ?? '')
  const [watching, setWatching] = useState<string | null>(searchParams.get('mandate'))

  const { data: merchants } = useMerchants()

  const recentMandates = usePolling(() => listMandatesForUser(userId as string), [userId], {
    enabled: userId !== null,
    intervalMs: 5000,
  })
  const today = (recentMandates.data ?? []).filter((m) => Date.now() - new Date(m.created_at).getTime() <= DAY_MS)

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
  const merchant = mandate.data ? merchants?.find((m) => m.merchant_id === mandate.data!.merchant_id) : undefined
  const theme = getMerchantTheme(merchant?.slug)

  const merchantName = (id: string) => merchants?.find((m: MerchantResponse) => m.merchant_id === id)?.name

  function open(mandateId: string) {
    setInput(mandateId)
    setWatching(mandateId)
  }

  return (
    <div className="max-w-2xl space-y-6">
      <div>
        <h1 className="text-lg font-semibold text-slate-900">AI Activity</h1>
        <p className="text-sm text-slate-500">
          Watch a buyer agent shop an AgentPay merchant over MCP in near-real-time.
        </p>
      </div>

      {/* Mandates authorized in the last 24 hours */}
      {userId && (
        <div className="rounded-lg border border-slate-200 bg-white">
          <div className="flex items-center justify-between border-b border-slate-100 px-4 py-2.5">
            <h2 className="text-sm font-semibold text-slate-700">Mandates · last 24 hours</h2>
            {today.length > 0 && <span className="text-xs text-slate-400">{today.length}</span>}
          </div>

          {recentMandates.loading && !recentMandates.data && (
            <p className="px-4 py-3 text-sm text-slate-500">Loading…</p>
          )}
          {recentMandates.data && today.length === 0 && (
            <p className="px-4 py-3 text-sm text-slate-500">No mandates authorized in the last 24 hours.</p>
          )}

          <ul className="divide-y divide-slate-100">
            {today.map((m) => {
              const name = merchantName(m.merchant_id)
              const active = watching === m.mandate_id
              return (
                <li key={m.mandate_id}>
                  <button
                    type="button"
                    onClick={() => open(m.mandate_id)}
                    className={`flex w-full items-center justify-between gap-3 px-4 py-3 text-left transition hover:bg-slate-50 ${
                      active ? 'bg-slate-50' : ''
                    }`}
                  >
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-sm text-slate-800">{m.mandate_id}</span>
                        {name && <span className="text-xs text-slate-400">{name}</span>}
                      </div>
                      <p className="mt-0.5 truncate text-xs text-slate-500">
                        {m.product_type} · up to {formatCurrency(m.max_amount_minor, m.currency)} · {timeAgo(m.created_at)}
                      </p>
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                      <StatusBadge status={m.status} />
                      <span aria-hidden className="text-slate-300">
                        →
                      </span>
                    </div>
                  </button>
                </li>
              )
            })}
          </ul>
        </div>
      )}

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
          placeholder="or paste a mandate_id, e.g. M-a1b2c3d4"
          className="flex-1 rounded-md border border-slate-300 px-3 py-2 font-mono text-sm"
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
                <div className="flex items-center gap-2">
                  <h2 className="text-sm font-semibold text-slate-700">Mandate {mandate.data.mandate_id}</h2>
                  {merchant && (
                    <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium text-white ${theme.primaryButton}`}>
                      {merchant.name}
                    </span>
                  )}
                </div>
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

          {activity.loading && !activity.data && <p className="text-sm text-slate-500">Loading…</p>}
          {activity.data && activity.data.length === 0 && (
            <p className="text-sm text-slate-500">No activity recorded yet for this mandate.</p>
          )}
          {activity.data && activity.data.length > 0 && <LiveConversation events={activity.data} cart={cart.data} />}
        </div>
      )}
    </div>
  )
}
