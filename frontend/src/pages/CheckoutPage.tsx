import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ActivityTimeline } from '../components/ActivityTimeline'
import { useBuyer } from '../context/BuyerContext'
import { useCart } from '../context/CartContext'
import { getMandateAuditEvents } from '../services/auditApi'
import { completePurchase, requestCheckout } from '../services/checkoutApi'
import { createMandate } from '../services/mandateApi'
import { getProduct } from '../services/productApi'
import { usePolling } from '../hooks/usePolling'
import { formatCurrency } from '../lib/formatCurrency'
import { openRazorpayCheckout } from '../lib/razorpay'
import type { CheckoutResponse } from '../types/checkout'

type Phase = 'review' | 'authorizing' | 'authorized' | 'paying' | 'failed'

/**
 * Checkout page: authorizes a mandate for the current cart, runs AgentPay's
 * deterministic checkout boundary, then opens Razorpay Standard Checkout
 * for the frozen cart (plan.md Section 18/22).
 */
export function CheckoutPage() {
  const { cart, clearCart } = useCart()
  const { email, name } = useBuyer()
  const navigate = useNavigate()

  const [phase, setPhase] = useState<Phase>('review')
  const [notes, setNotes] = useState('')
  const [allowAddons, setAllowAddons] = useState(false)
  const [mandateId, setMandateId] = useState<string | null>(null)
  const [checkoutResult, setCheckoutResult] = useState<CheckoutResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  const activity = usePolling(() => getMandateAuditEvents(mandateId as string), [mandateId], {
    enabled: mandateId !== null,
    intervalMs: 2000,
  })

  if (!cart || cart.items.length === 0) {
    return <p className="text-sm text-slate-500">Your cart is empty.</p>
  }

  async function handleAuthorize() {
    if (!cart || !email) return
    setPhase('authorizing')
    setError(null)
    try {
      const products = await Promise.all(cart.items.map((item) => getProduct(item.product_id)))
      const categories = [...new Set(products.map((product) => product.category))]
      const productNames = [...new Set(cart.items.map((item) => item.product_name))]
      const mandate = await createMandate({
        user_email: email,
        user_name: name,
        merchant_id: cart.merchant_id,
        currency: cart.currency,
        max_amount_minor: cart.subtotal_minor,
        allowed_categories: categories,
        allow_addons: allowAddons,
        delivery_requirement: 'under_3_days',
        single_use: true,
        expires_in_hours: 1,
        product_type: productNames.join(', ') || 'general purchase',
        notes: notes || null,
      })
      setMandateId(mandate.mandate_id)
      const result = await requestCheckout(cart.cart_id, mandate.mandate_id)
      setCheckoutResult(result)
      setPhase('authorized')
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
      setPhase('review')
    }
  }

  async function handlePay() {
    if (!cart || !mandateId || !checkoutResult) return
    setPhase('paying')
    setError(null)
    try {
      const session = await completePurchase(cart.cart_id, mandateId)
      await openRazorpayCheckout({
        keyId: session.razorpay_key_id,
        razorpayOrderId: session.razorpay_order_id,
        amountMinor: session.amount_minor,
        currency: session.currency,
        buyerName: name,
        buyerEmail: email ?? '',
        onSuccess: () => {
          clearCart()
          navigate(`/order/${session.order_id}?mandate=${mandateId}`)
        },
        onFailure: (reason) => {
          setError(reason)
          setPhase('authorized')
        },
        onDismiss: () => setPhase('authorized'),
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
      setPhase('authorized')
    }
  }

  return (
    <div className="max-w-xl space-y-6">
      <h1 className="text-lg font-semibold text-slate-900">Checkout</h1>

      <div className="rounded-lg border border-slate-200 bg-white p-4">
        <ul className="divide-y divide-slate-100 text-sm">
          {(checkoutResult?.cart ?? cart).items.map((item) => (
            <li key={item.item_id} className="flex items-center justify-between py-2">
              <span>
                {item.product_name} × {item.quantity}
              </span>
              <span className="font-medium text-slate-900">{formatCurrency(item.line_total_minor, cart.currency)}</span>
            </li>
          ))}
        </ul>
        <div className="mt-2 flex items-center justify-between border-t border-slate-100 pt-2 text-sm font-semibold">
          <span>Total</span>
          <span>{formatCurrency((checkoutResult?.cart ?? cart).subtotal_minor, cart.currency)}</span>
        </div>
      </div>

      {phase === 'review' && (
        <div className="space-y-3 rounded-lg border border-slate-200 bg-white p-4">
          <label className="block text-sm">
            <span className="text-slate-600">Notes for the merchant (optional)</span>
            <input
              type="text"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
              placeholder="e.g. no unnecessary accessories"
            />
          </label>
          <label className="flex items-center gap-2 text-sm text-slate-600">
            <input type="checkbox" checked={allowAddons} onChange={(e) => setAllowAddons(e.target.checked)} />
            Allow the merchant to propose add-ons
          </label>
          <button
            type="button"
            onClick={() => void handleAuthorize()}
            className="w-full rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white"
          >
            Authorize purchase
          </button>
        </div>
      )}

      {phase === 'authorizing' && <p className="text-sm text-slate-500">Authorizing mandate and freezing cart…</p>}

      {(phase === 'authorized' || phase === 'paying') && checkoutResult && (
        <div className="space-y-4">
          {checkoutResult.proposal && checkoutResult.proposal.status !== 'NO_PROPOSAL' && (
            <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
              Merchant proposal: {checkoutResult.proposal.status}
              {checkoutResult.proposal.reason ? ` — ${checkoutResult.proposal.reason}` : ''}
            </div>
          )}
          <div className="rounded-lg border border-slate-200 bg-white p-4">
            <h2 className="mb-3 text-sm font-semibold text-slate-700">AgentPay activity</h2>
            {activity.data && <ActivityTimeline events={activity.data} />}
          </div>
          <button
            type="button"
            disabled={phase === 'paying'}
            onClick={() => void handlePay()}
            className="w-full rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            {phase === 'paying' ? 'Opening Razorpay…' : `Pay ${formatCurrency(checkoutResult.cart.subtotal_minor, cart.currency)}`}
          </button>
        </div>
      )}

      {error && <p className="text-sm text-red-600">{error}</p>}
    </div>
  )
}
