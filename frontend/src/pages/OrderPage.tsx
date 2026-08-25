import { Link, useParams, useSearchParams } from 'react-router-dom'
import { ActivityTimeline } from '../components/ActivityTimeline'
import { usePolling } from '../hooks/usePolling'
import { getMandateAuditEvents } from '../services/auditApi'

/**
 * Order confirmation page: polls the mandate's audit trail so the buyer
 * watches AgentPay/Razorpay finish settling the payment (the webhook is the
 * authoritative completion signal, not the Razorpay widget's own callback).
 */
export function OrderPage() {
  const { orderId } = useParams<{ orderId: string }>()
  const [searchParams] = useSearchParams()
  const mandateId = searchParams.get('mandate')

  const activity = usePolling(() => getMandateAuditEvents(mandateId as string), [mandateId], {
    enabled: mandateId !== null,
    intervalMs: 2000,
  })

  const events = activity.data ?? []
  const captured = events.some((e) => e.event_type === 'PAYMENT_CAPTURED')
  const failed = events.some((e) => ['PAYMENT_FAILED', 'TRANSACTION_BLOCKED'].includes(e.event_type))

  return (
    <div className="max-w-xl space-y-4">
      <h1 className="text-lg font-semibold text-slate-900">Order confirmation</h1>
      <p className="font-mono text-xs text-slate-500">order_id: {orderId}</p>

      {captured && (
        <p className="rounded-md bg-emerald-50 px-3 py-2 text-sm text-emerald-800">Payment captured — order complete.</p>
      )}
      {failed && <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-800">Payment did not succeed.</p>}
      {!captured && !failed && (
        <p className="rounded-md bg-slate-100 px-3 py-2 text-sm text-slate-600">Waiting for payment confirmation…</p>
      )}

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
