import { Link, useParams } from 'react-router-dom'
import { AuditTimeline } from '../components/AuditTimeline'
import { StatusBadge } from '../components/StatusBadge'
import { useAuditEvents, useAuditVerification } from '../hooks/useAudit'

/** The audit hash-chain viewer for one transaction (plan.md Section 19.2/24 "Audit viewer"). */
export function AuditPage() {
  const { transactionId } = useParams<{ transactionId: string }>()
  const events = useAuditEvents(transactionId ?? '')
  const verification = useAuditVerification(transactionId ?? '')

  return (
    <div className="space-y-6">
      <div>
        <Link to={`/console/transactions/${transactionId}`} className="text-sm text-slate-500 hover:text-slate-700">
          ← Back to transaction
        </Link>
        <h1 className="mt-1 text-lg font-semibold text-slate-900">Audit Chain</h1>
      </div>

      <div className="rounded-lg border border-slate-200 bg-white p-4">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-slate-800">Chain Integrity</h3>
          {verification.loading && <span className="text-sm text-slate-500">Verifying…</span>}
          {verification.data && <StatusBadge status={verification.data.valid ? 'VALID' : 'INVALID'} />}
        </div>
        {verification.error && <p className="mt-2 text-sm text-red-600">{verification.error.message}</p>}
        {verification.data && (
          <p className="mt-2 text-sm text-slate-500">
            {verification.data.events_checked} event(s) checked across the full system-wide chain.
            {!verification.data.valid && verification.data.first_mismatch && (
              <>
                {' '}
                First mismatch at position {verification.data.first_mismatch.position}:{' '}
                {verification.data.first_mismatch.reason}
              </>
            )}
          </p>
        )}
      </div>

      <div className="rounded-lg border border-slate-200 bg-white p-4">
        <h3 className="mb-3 text-sm font-semibold text-slate-800">Events</h3>
        {events.loading && <p className="text-sm text-slate-500">Loading…</p>}
        {events.error && <p className="text-sm text-red-600">{events.error.message}</p>}
        {events.data && <AuditTimeline events={events.data} />}
      </div>
    </div>
  )
}
