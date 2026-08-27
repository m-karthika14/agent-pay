/**
 * Global "Claude wants to buy" popup (plan.md Phase 2).
 *
 * Polls GET /api/authorization-requests/by-user/{userId} for a real,
 * backend-persisted PENDING request -- never frontend-only state -- so it
 * shows up on any page, survives a refresh, and clears itself the moment
 * the request is no longer PENDING (approved/rejected from here or from
 * anywhere else).
 *
 * Also fires a real browser Notification (the OS-level toast, not just
 * something rendered inside the page) the moment a new request appears --
 * so it's noticeable even if this tab is in the background or you're
 * looking at a different tab in the same browser. This only works while
 * the browser itself is open with this tab present somewhere and
 * notification permission has been granted for this site; it cannot reach
 * a different browser/device or survive the browser being fully closed --
 * that would need a real Web Push subscription + backend infrastructure,
 * a deliberately bigger feature this is not.
 */
import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useBuyer } from '../context/BuyerContext'
import { cartIdStorageKey } from '../context/CartContext'
import { useMerchants } from '../hooks/useMerchants'
import { useProducts } from '../hooks/useProducts'
import { usePolling } from '../hooks/usePolling'
import * as cartApi from '../services/cartApi'
import * as authorizationApi from '../services/authorizationApi'
import { formatCurrency } from '../lib/formatCurrency'
import { getMerchantTheme } from '../lib/merchantTheme'
import type { AuthorizationRequestResponse } from '../types/authorization'
import type { MerchantResponse } from '../types/merchant'

/** Ask for notification permission once per buyer session, as soon as we know who's logged in. Browsers that require a direct click gesture (e.g. Safari) may silently ignore this -- the in-page popup still works either way. */
function useNotificationPermission(userId: string | null) {
  useEffect(() => {
    if (!userId) return
    if (typeof Notification === 'undefined') return
    if (Notification.permission === 'default') void Notification.requestPermission()
  }, [userId])
}

/** Fire a real OS-level notification the first time a given request_id is seen as PENDING -- never re-fires for the same request on later polls. */
function useNewRequestNotification(request: AuthorizationRequestResponse | null) {
  const notified = useRef<Set<string>>(new Set())

  useEffect(() => {
    if (!request) return
    if (typeof Notification === 'undefined' || Notification.permission !== 'granted') return
    if (notified.current.has(request.request_id)) return
    notified.current.add(request.request_id)

    const notification = new Notification('🤖 Claude wants to buy', {
      body: `${request.product_type} — up to ${formatCurrency(request.max_amount_minor, 'INR')}`,
      tag: request.request_id,
    })
    notification.onclick = () => {
      window.focus()
      notification.close()
    }
  }, [request])
}

/** Polls for a pending Claude authorization request and, if one exists, renders the popup card and fires a browser notification. */
export function GlobalAuthorizationPopup() {
  const { userId } = useBuyer()
  const { data: merchants } = useMerchants()
  const pending = usePolling(
    () => authorizationApi.listPendingAuthorizationRequests(userId as string),
    [userId],
    { enabled: !!userId, intervalMs: 3000 },
  )

  const request = pending.data?.[0] ?? null
  useNotificationPermission(userId)
  useNewRequestNotification(request)

  if (!request || !merchants) return null

  return <PopupCard key={request.request_id} request={request} merchants={merchants} />
}

function PopupCard({ request, merchants }: { request: AuthorizationRequestResponse; merchants: MerchantResponse[] }) {
  const navigate = useNavigate()
  const cart = usePolling(() => cartApi.getCart(request.cart_id), [request.cart_id], { intervalMs: 60_000 })

  const [editing, setEditing] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [dismissed, setDismissed] = useState(false)

  const merchant = cart.data ? merchants.find((m) => m.merchant_id === cart.data!.merchant_id) : undefined
  const theme = getMerchantTheme(merchant?.slug)

  if (dismissed || !cart.data) return null

  async function handleReject() {
    setSubmitting(true)
    setError(null)
    try {
      await authorizationApi.rejectAuthorizationRequest(request.request_id)
      setDismissed(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setSubmitting(false)
    }
  }

  function handleReview() {
    if (!merchant) return
    localStorage.setItem(cartIdStorageKey(merchant.slug), request.cart_id)
    navigate(`/store/${merchant.slug}/cart`)
  }

  async function handleApprove(terms: {
    maxAmountMinor: number
    allowedCategories: string[]
    allowAddons: boolean
    notes: string | null
  }) {
    setSubmitting(true)
    setError(null)
    try {
      await authorizationApi.approveAuthorizationRequest(request.request_id, {
        product_type: request.product_type,
        max_amount_minor: terms.maxAmountMinor,
        allowed_categories: terms.allowedCategories,
        allow_addons: terms.allowAddons,
        delivery_requirement: request.delivery_requirement,
        single_use: request.single_use,
        expires_in_hours: request.expires_in_hours,
        notes: terms.notes,
      })
      setDismissed(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="fixed top-20 left-1/2 z-50 w-full max-w-md -translate-x-1/2 px-4">
      <div className="space-y-4 rounded-2xl border border-slate-200 bg-white p-5 shadow-2xl">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-xs font-semibold tracking-wide text-slate-400 uppercase">Claude wants to buy</p>
            <h2 className="text-base font-semibold text-slate-900">{merchant?.name ?? 'a merchant'}</h2>
          </div>
          <span className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-medium text-white ${theme.primaryButton}`}>
            🤖 Claude
          </span>
        </div>

        {request.reason && <p className="text-sm text-slate-600 italic">"{request.reason}"</p>}

        <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
          <ul className="divide-y divide-slate-200 text-sm">
            {cart.data.items.map((item) => (
              <li key={item.item_id} className="flex items-center justify-between py-1.5">
                <span>
                  {item.product_name} × {item.quantity}
                </span>
                <span className="font-medium text-slate-900">{formatCurrency(item.line_total_minor, cart.data!.currency)}</span>
              </li>
            ))}
            {cart.data.items.length === 0 && <li className="py-1.5 text-slate-400">(cart is empty so far)</li>}
          </ul>
        </div>

        {!editing ? (
          <dl className="grid grid-cols-2 gap-2 text-sm">
            <div>
              <dt className="text-xs text-slate-400">Max spending</dt>
              <dd className="font-medium text-slate-800">{formatCurrency(request.max_amount_minor, cart.data.currency)}</dd>
            </div>
            <div>
              <dt className="text-xs text-slate-400">Categories</dt>
              <dd className="font-medium text-slate-800 capitalize">{request.allowed_categories.join(', ') || '—'}</dd>
            </div>
            <div className="col-span-2">
              <dt className="text-xs text-slate-400">Add-ons</dt>
              <dd className="font-medium text-slate-800">{request.allow_addons ? 'Allowed' : 'Not allowed'}</dd>
            </div>
          </dl>
        ) : (
          <EditForm
            request={request}
            merchantSlug={merchant?.slug}
            submitting={submitting}
            onCancel={() => setEditing(false)}
            onSubmit={handleApprove}
          />
        )}

        {error && <p className="text-sm text-red-600">{error}</p>}

        {!editing && (
          <div className="flex gap-2">
            <button
              type="button"
              disabled={submitting}
              onClick={() => void handleReject()}
              className="flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-50 disabled:opacity-40"
            >
              Reject
            </button>
            <button
              type="button"
              disabled={submitting || !merchant}
              onClick={handleReview}
              className="flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-50 disabled:opacity-40"
            >
              Review
            </button>
            <button
              type="button"
              disabled={submitting}
              onClick={() => setEditing(true)}
              className="flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-50 disabled:opacity-40"
            >
              Edit
            </button>
            <button
              type="button"
              disabled={submitting}
              onClick={() =>
                void handleApprove({
                  maxAmountMinor: request.max_amount_minor,
                  allowedCategories: request.allowed_categories,
                  allowAddons: request.allow_addons,
                  notes: request.notes,
                })
              }
              className={`flex-1 rounded-md px-3 py-2 text-sm font-medium text-white transition disabled:opacity-40 ${theme.primaryButton}`}
            >
              Approve
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

function EditForm({
  request,
  merchantSlug,
  submitting,
  onCancel,
  onSubmit,
}: {
  request: AuthorizationRequestResponse
  merchantSlug: string | undefined
  submitting: boolean
  onCancel: () => void
  onSubmit: (terms: { maxAmountMinor: number; allowedCategories: string[]; allowAddons: boolean; notes: string | null }) => void
}) {
  const { data: products } = useProducts(merchantSlug)
  const categories = [...new Set((products ?? []).map((p) => p.category))].sort()

  const [maxAmount, setMaxAmount] = useState(String(request.max_amount_minor / 100))
  const [selectedCategories, setSelectedCategories] = useState<Set<string>>(new Set(request.allowed_categories))
  const [allowAddons, setAllowAddons] = useState(request.allow_addons)
  const [notes, setNotes] = useState(request.notes ?? '')

  function toggleCategory(category: string) {
    setSelectedCategories((prev) => {
      const next = new Set(prev)
      if (next.has(category)) next.delete(category)
      else next.add(category)
      return next
    })
  }

  return (
    <div className="space-y-3 rounded-lg border border-slate-200 bg-slate-50 p-3">
      <label className="block text-sm">
        <span className="text-slate-600">Maximum spending (₹)</span>
        <input
          type="number"
          min="1"
          step="1"
          value={maxAmount}
          onChange={(e) => setMaxAmount(e.target.value)}
          className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
        />
      </label>
      <fieldset>
        <legend className="text-sm text-slate-600">Allowed categories</legend>
        <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1.5">
          {categories.map((category) => (
            <label key={category} className="flex items-center gap-1.5 text-sm text-slate-700 capitalize">
              <input type="checkbox" checked={selectedCategories.has(category)} onChange={() => toggleCategory(category)} />
              {category}
            </label>
          ))}
        </div>
      </fieldset>
      <label className="flex items-center gap-2 text-sm text-slate-600">
        <input type="checkbox" checked={allowAddons} onChange={(e) => setAllowAddons(e.target.checked)} />
        Allow the merchant to propose add-ons
      </label>
      <label className="block text-sm">
        <span className="text-slate-600">Notes (optional)</span>
        <input
          type="text"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
        />
      </label>
      <div className="flex gap-2 pt-1">
        <button
          type="button"
          onClick={onCancel}
          className="flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-white"
        >
          Cancel
        </button>
        <button
          type="button"
          disabled={submitting || selectedCategories.size === 0 || Number(maxAmount) <= 0}
          onClick={() =>
            onSubmit({
              maxAmountMinor: Math.round(Number(maxAmount) * 100),
              allowedCategories: [...selectedCategories],
              allowAddons,
              notes: notes || null,
            })
          }
          className="flex-1 rounded-md bg-slate-900 px-3 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-40"
        >
          {submitting ? 'Approving…' : 'Approve edited terms'}
        </button>
      </div>
    </div>
  )
}
