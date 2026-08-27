import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { LiveConversation } from '../components/LiveConversation'
import { useBuyer } from '../context/BuyerContext'
import { useCart } from '../context/CartContext'
import { useMerchants } from '../hooks/useMerchants'
import { ApiRequestError } from '../services/apiClient'
import { getMandateAuditEvents } from '../services/auditApi'
import { completePurchase, requestCheckout } from '../services/checkoutApi'
import { createMandate } from '../services/mandateApi'
import { getProduct } from '../services/productApi'
import { usePolling } from '../hooks/usePolling'
import { formatCurrency } from '../lib/formatCurrency'
import { getMerchantTheme } from '../lib/merchantTheme'
import { relatedCategoriesFor } from '../lib/relatedCategories'
import { openRazorpayCheckout } from '../lib/razorpay'
import type { CheckoutResponse } from '../types/checkout'

type Phase = 'review' | 'authorizing' | 'authorized' | 'paying' | 'failed'

/**
 * Checkout page: authorizes a mandate for the current cart, runs AgentPay's
 * deterministic checkout boundary, then opens Razorpay Standard Checkout
 * for the frozen cart (plan.md Section 18/22).
 */
export function CheckoutPage() {
  const { merchantSlug } = useParams<{ merchantSlug: string }>()
  const { cart, clearCart } = useCart()
  const { email, name } = useBuyer()
  const { data: merchants } = useMerchants()
  const navigate = useNavigate()
  const theme = getMerchantTheme(merchantSlug)
  const merchantName = merchants?.find((m) => m.slug === merchantSlug)?.name ?? merchantSlug ?? 'AgentPay'

  const [phase, setPhase] = useState<Phase>('review')
  const [mandateId, setMandateId] = useState<string | null>(null)
  const [checkoutResult, setCheckoutResult] = useState<CheckoutResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  const activity = usePolling(() => getMandateAuditEvents(mandateId as string), [mandateId], {
    enabled: mandateId !== null,
    intervalMs: 2000,
  })

  useEffect(() => {
    // Recovers from navigating away and back to /checkout (or a page
    // refresh) after already authorizing: this page's own `phase` state
    // resets to 'review' on every mount, but the cart stayed FROZEN on the
    // backend -- without this, clicking "Authorize purchase" again would
    // hit IDEMPOTENCY_DUPLICATE on an already-checked-out cart instead of
    // just picking back up where it left off.
    if (phase === 'review' && cart && cart.status === 'FROZEN' && cart.mandate_id && cart.frozen_hash && cart.frozen_at) {
      setMandateId(cart.mandate_id)
      setCheckoutResult({ cart, frozen_hash: cart.frozen_hash, frozen_at: cart.frozen_at, proposal: null })
      setPhase('authorized')
    }
    // phase intentionally excluded: this should only react to `cart`
    // becoming available/changing, not re-run every time phase itself
    // changes (which would include changes this same effect just made).
  }, [cart])

  if (!cart || cart.items.length === 0) {
    return <p className="text-sm text-slate-500">Your cart is empty.</p>
  }

  async function handleAuthorize() {
    if (!cart || !email) return
    setPhase('authorizing')
    setError(null)
    try {
      let result
      let usedMandateId: string
      try {
        // If Claude already got this exact cart approved via the "Claude
        // wants to buy" popup, reuse that mandate instead of creating a
        // second, redundant one of our own -- AgentPay resolves it from the
        // cart's own already-approved authorization request (plan.md Phase
        // 2.1). Without this, clicking "Authorize purchase" here on a cart
        // Claude already got approved created a competing mandate and could
        // race Claude's own in-flight checkout call.
        result = await requestCheckout(cart.cart_id)
        usedMandateId = result.cart.mandate_id as string
      } catch (err) {
        if (!(err instanceof ApiRequestError && err.code === 'NO_APPROVED_AUTHORIZATION')) throw err
        // No existing approval for this cart -- a genuine direct-checkout
        // cart with no Claude involvement. Create a mandate now, same as before.
        const products = await Promise.all(cart.items.map((item) => getProduct(item.product_id)))
        const categories = [...new Set(products.map((product) => product.category))]
        const productNames = [...new Set(cart.items.map((item) => item.product_name))]
        const mandate = await createMandate({
          user_email: email,
          user_name: name ?? undefined,
          merchant_id: cart.merchant_id,
          currency: cart.currency,
          // 25% headroom above the cart's own subtotal -- a mandate that caps
          // out at exactly the cart total leaves zero room for any upsell to
          // ever mathematically fit, regardless of category permission
          // (verified live: a real cart hit this exact wall). Comfortably
          // covers this catalog's real accessory prices (Rs 199-599).
          max_amount_minor: Math.round(cart.subtotal_minor * 1.25),
          // Always include related add-on categories (e.g. accessories for
          // an audio purchase) and always allow the merchant to propose one
          // -- the Merchant Agent should always get a real chance to try;
          // AgentPay's own category/amount checks still decide whether any
          // specific proposal is actually accepted.
          allowed_categories: [...new Set([...categories, ...relatedCategoriesFor(categories)])],
          allow_addons: true,
          delivery_requirement: 'under_3_days',
          single_use: true,
          expires_in_hours: 1,
          product_type: productNames.join(', ') || 'general purchase',
          notes: null,
        })
        usedMandateId = mandate.mandate_id
        result = await requestCheckout(cart.cart_id, mandate.mandate_id)
      }
      setMandateId(usedMandateId)
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
        buyerName: name ?? 'Storefront Buyer',
        buyerEmail: email ?? '',
        storeName: merchantName,
        themeColor: theme.razorpayColor,
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
          <button
            type="button"
            disabled={!email}
            onClick={() => void handleAuthorize()}
            className={`w-full rounded-md px-4 py-2 text-sm font-medium text-white transition disabled:opacity-40 ${theme.primaryButton}`}
          >
            Authorize purchase
          </button>
        </div>
      )}

      {phase === 'authorizing' && <p className="text-sm text-slate-500">Authorizing mandate and freezing cart…</p>}

      {(phase === 'authorized' || phase === 'paying') && checkoutResult && (
        <div className="space-y-4">
          {activity.data && <LiveConversation events={activity.data} cart={checkoutResult.cart} />}
          <button
            type="button"
            disabled={phase === 'paying'}
            onClick={() => void handlePay()}
            className={`w-full rounded-md px-4 py-2 text-sm font-medium text-white transition disabled:opacity-50 ${theme.primaryButton}`}
          >
            {phase === 'paying' ? 'Opening Razorpay…' : `Pay ${formatCurrency(checkoutResult.cart.subtotal_minor, cart.currency)}`}
          </button>
        </div>
      )}

      {error && <p className="text-sm text-red-600">{error}</p>}
    </div>
  )
}
