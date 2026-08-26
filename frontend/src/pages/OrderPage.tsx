import { useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { ActivityTimeline } from '../components/ActivityTimeline'
import { usePolling } from '../hooks/usePolling'
import { getMandateAuditEvents } from '../services/auditApi'
import { syncOrder } from '../services/orderApi'

/**
 * Order confirmation page: polls the mandate's audit trail so the buyer
 * watches AgentPay/Razorpay finish settling the payment (the webhook is the
 * authoritative completion signal, not the Razorpay widget's own callback).
 *
 * "Check payment status" is a manual fallback for when that webhook can't
 * reach the backend at all (e.g. a local dev server with no public URL) --
 * it re-checks directly against Razorpay and corrects AgentPay's stored
 * state if a delivery was missed.
 */
export function OrderPage() {
  const { orderId } = useParams<{ orderId: string }>()
  const [searchParams] = useSearchParams()
  const mandateId = searchParams.get('mandate')
  const [syncing, setSyncing] = useState(false)
  const [syncError, setSyncError] = useState<string | null>(null)

  const activity = usePolling(() => getMandateAuditEvents(mandateId as string), [mandateId], {
    enabled: mandateId !== null,
    intervalMs: 2000,
  })

  const events = activity.data ?? []
  const captured = events.some((e) => e.event_type === 'PAYMENT_CAPTURED')
  const failed = events.some((e) => ['PAYMENT_FAILED', 'TRANSACTION_BLOCKED'].includes(e.event_type))

  async function handleCheckStatus() {
    if (!orderId) return
    setSyncing(true)
    setSyncError(null)
    try {
      await syncOrder(orderId)
      // The next poll tick (within 2s) picks up whatever sync corrected --
      // no separate refetch call needed.
    } catch (err) {
      setSyncError(err instanceof Error ? err.message : String(err))
    } finally {
      setSyncing(false)
    }
  }

  return (
    <div className="max-w-xl space-y-4">
      <h1 className="text-lg font-semibold text-slate-900">Order confirmation</h1>
      <p className="font-mono text-xs text-slate-500">order_id: {orderId}</p>

      {captured && (
        <p className="rounded-md bg-emerald-50 px-3 py-2 text-sm text-emerald-800">Payment captured — order complete.</p>
      )}
      {failed && <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-800">Payment did not succeed.</p>}
      {!captured && !failed && (
        <div className="flex items-center justify-between gap-3 rounded-md bg-slate-100 px-3 py-2 text-sm text-slate-600">
          <span>Waiting for payment confirmation…</span>
          <button
            type="button"
            disabled={syncing || !orderId}
            onClick={() => void handleCheckStatus()}
            className="shrink-0 rounded-md bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white transition hover:bg-indigo-700 disabled:opacity-40"
          >
            {syncing ? 'Checking…' : 'Check payment status'}
          </button>
        </div>
      )}
      {syncError && <p className="text-sm text-red-600">{syncError}</p>}

      {mandateId && (
        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <h2 className="mb-3 text-sm font-semibold text-slate-700">AgentPay activity</h2>
          {events.length > 0 ? <ActivityTimeline events={events} /> : <p className="text-sm text-slate-500">Loading…</p>}
        </div>
      )}

      <Link to="/" className="inline-block text-sm font-medium text-slate-900 underline">
        Continue shopping
      </Link>
    </div>
  )
}
