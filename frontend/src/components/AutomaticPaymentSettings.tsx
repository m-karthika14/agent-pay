/**
 * A user's own "Automatic Payments" authorization (plan.md Phase 5) --
 * HOW AgentPay is permitted to pay, set here on the landing page beside the
 * AI Shopping Budget (types/budget.ts) but deliberately a separate control:
 * the budget is WHAT the AI may spend; this is HOW AgentPay is authorized
 * to actually move money. Both must be valid before AgentPay ever executes
 * payment automatically -- see app.payments.authorization_service's
 * module docstring on the backend.
 *
 * Setup is the ONE interactive Razorpay Checkout step (full authentication,
 * never bypassed) that registers a reusable payment token; nothing here (or
 * on the backend) ever sees or stores a raw card/UPI/bank credential.
 */
import { useState } from 'react'
import { useBuyer } from '../context/BuyerContext'
import { usePolling } from '../hooks/usePolling'
import * as paymentAuthorizationApi from '../services/paymentAuthorizationApi'
import { formatCurrency } from '../lib/formatCurrency'
import { openRazorpayCheckout } from '../lib/razorpay'
import type { PaymentAuthorizationResponse } from '../types/paymentAuthorization'

export function AutomaticPaymentSettings({ userId }: { userId: string }) {
  const [refreshKey, setRefreshKey] = useState(0)
  const [expanded, setExpanded] = useState(false)
  const auth = usePolling(() => paymentAuthorizationApi.getPaymentAuthorization(userId), [userId, refreshKey], {
    intervalMs: 60_000,
  })

  if (!auth.data) return null

  const refresh = () => setRefreshKey((k) => k + 1)

  if (!expanded) {
    return (
      <div className="flex justify-center">
        {auth.data.is_active ? (
          <div className="flex items-center gap-2 rounded-full border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs text-slate-600">
            <span>
              💳 Automatic payments: <span className="font-medium text-slate-800">Active</span>
              {auth.data.max_amount_minor !== null && auth.data.currency
                ? ` · up to ${formatCurrency(auth.data.max_amount_minor, auth.data.currency)}`
                : ''}
            </span>
            <button type="button" onClick={() => setExpanded(true)} className="font-medium text-slate-500 underline hover:text-slate-700">
              Manage
            </button>
          </div>
        ) : (
          <button
            type="button"
            onClick={() => setExpanded(true)}
            className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-100"
          >
            💳 Set up automatic payments
          </button>
        )}
      </div>
    )
  }

  return (
    <AutomaticPaymentPanel
      userId={userId}
      current={auth.data}
      onDone={() => {
        setExpanded(false)
        refresh()
      }}
      onCancel={() => setExpanded(false)}
    />
  )
}

function AutomaticPaymentPanel({
  userId,
  current,
  onDone,
  onCancel,
}: {
  userId: string
  current: PaymentAuthorizationResponse
  onDone: () => void
  onCancel: () => void
}) {
  const { name, email } = useBuyer()
  const [maxAmount, setMaxAmount] = useState(
    current.max_amount_minor !== null ? String(current.max_amount_minor / 100) : '10000',
  )
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleAuthorize() {
    setSubmitting(true)
    setError(null)
    try {
      const setup = await paymentAuthorizationApi.setupPaymentAuthorization(userId, {
        max_amount_minor: Math.round(Number(maxAmount) * 100),
        currency: 'INR',
      })
      await openRazorpayCheckout({
        keyId: setup.razorpay_key_id,
        razorpayOrderId: setup.razorpay_order_id,
        amountMinor: setup.amount_minor,
        currency: setup.currency,
        buyerName: name ?? 'AgentPay Buyer',
        buyerEmail: email ?? '',
        storeName: 'AgentPay',
        // This is the recurring-token registration transaction -- Razorpay
        // only issues a reusable e-mandate token when Checkout is opened
        // with recurring:1 and the registration order's customer_id.
        recurring: true,
        customerId: setup.razorpay_customer_id,
        onSuccess: (paymentId) => {
          void (async () => {
            try {
              await paymentAuthorizationApi.confirmPaymentAuthorization(userId, {
                razorpay_order_id: setup.razorpay_order_id,
                razorpay_payment_id: paymentId,
              })
              onDone()
            } catch (err) {
              setError(err instanceof Error ? err.message : String(err))
              setSubmitting(false)
            }
          })()
        },
        onFailure: (reason) => {
          setError(reason)
          setSubmitting(false)
        },
        onDismiss: () => setSubmitting(false),
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
      setSubmitting(false)
    }
  }

  async function handleRevoke() {
    setSubmitting(true)
    setError(null)
    try {
      await paymentAuthorizationApi.revokePaymentAuthorization(userId)
      onDone()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
      setSubmitting(false)
    }
  }

  if (current.is_active) {
    return (
      <div className="mx-auto max-w-xs space-y-3 rounded-2xl border border-slate-200 bg-white p-4 text-left shadow-sm">
        <p className="text-center text-xs font-semibold tracking-wide text-slate-400 uppercase">💳 Automatic Payments</p>
        <dl className="grid grid-cols-2 gap-2 text-sm">
          <div>
            <dt className="text-xs text-slate-400">Status</dt>
            <dd className="font-medium text-emerald-700">✓ Active</dd>
          </div>
          <div>
            <dt className="text-xs text-slate-400">Provider</dt>
            <dd className="font-medium text-slate-800 capitalize">{current.provider ?? 'Razorpay'}</dd>
          </div>
          {current.max_amount_minor !== null && current.currency && (
            <div>
              <dt className="text-xs text-slate-400">Per-transaction limit</dt>
              <dd className="font-medium text-slate-800">{formatCurrency(current.max_amount_minor, current.currency)}</dd>
            </div>
          )}
          {current.authorized_at && (
            <div>
              <dt className="text-xs text-slate-400">Authorized</dt>
              <dd className="font-medium text-slate-800">{new Date(current.authorized_at).toLocaleDateString()}</dd>
            </div>
          )}
        </dl>
        <p className="text-xs text-slate-500">
          AgentPay may automatically complete eligible AI purchases within your AI Shopping Budget without a manual "Pay" step.
        </p>
        {error && <p className="text-sm text-red-600">{error}</p>}
        <div className="flex gap-2 pt-1">
          <button
            type="button"
            onClick={onCancel}
            className="flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            Close
          </button>
          <button
            type="button"
            disabled={submitting}
            onClick={() => void handleRevoke()}
            className="flex-1 rounded-md border border-red-300 px-3 py-2 text-sm font-medium text-red-700 hover:bg-red-50 disabled:opacity-40"
          >
            {submitting ? 'Revoking…' : 'Revoke automatic payments'}
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-xs space-y-3 rounded-2xl border border-slate-200 bg-white p-4 text-left shadow-sm">
      <p className="text-center text-xs font-semibold tracking-wide text-slate-400 uppercase">💳 Set up Automatic Payments</p>
      <p className="text-xs text-slate-500">
        AgentPay can automatically complete AI purchases after all of your spending and security rules pass -- never before.
      </p>
      <label className="block text-sm">
        <span className="text-slate-600">Maximum per transaction (₹)</span>
        <input
          type="number"
          min="1"
          step="1"
          value={maxAmount}
          onChange={(e) => setMaxAmount(e.target.value)}
          className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
        />
      </label>
      <div className="text-sm">
        <span className="text-slate-600">Payment method</span>
        <p className="mt-1 font-medium text-slate-800">Razorpay</p>
      </div>
      {error && <p className="text-sm text-red-600">{error}</p>}
      <div className="flex gap-2 pt-1">
        <button
          type="button"
          onClick={onCancel}
          className="flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
        >
          Cancel
        </button>
        <button
          type="button"
          disabled={submitting || Number(maxAmount) <= 0}
          onClick={() => void handleAuthorize()}
          className="flex-1 rounded-md bg-slate-900 px-3 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-40"
        >
          {submitting ? 'Opening Razorpay…' : 'Authorize payment method'}
        </button>
      </div>
    </div>
  )
}
