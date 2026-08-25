import { formatDate } from '../lib/formatDate'
import { StatusBadge } from './StatusBadge'
import type { TransactionTraceEvent } from '../types/transaction'

interface DecisionTraceProps {
  events: TransactionTraceEvent[]
}

/**
 * One transaction's ordered decision trace (plan.md Section 24 "Decision
 * trace": "Hard checks -> PASS, Merchant proposal -> ..., Intent gate ->
 * BLOCK, Reason -> ...").
 *
 * reason_code is shown as the reason. The original free-text reason a
 * merchant proposal or intent-gate call produced is never persisted past
 * the request that produced it (app.audit.service stores only a
 * payload_hash, not the raw payload -- see TransactionTraceResponse's
 * docstring), so the stable, documented reason-code vocabulary
 * (app.policy.reason_codes) is what's actually available to show here.
 */
export function DecisionTrace({ events }: DecisionTraceProps) {
  if (events.length === 0) {
    return <p className="text-sm text-slate-500">No decision events recorded for this transaction.</p>
  }
  return (
    <ol className="space-y-3">
      {events.map((event, index) => (
        <li key={`${event.event_type}-${index}`} className="flex items-start gap-3">
          <span className="mt-0.5 flex h-6 w-6 flex-none items-center justify-center rounded-full bg-slate-100 text-xs font-medium text-slate-500">
            {index + 1}
          </span>
          <div className="flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium text-slate-800">{event.event_type}</span>
              {event.decision && <StatusBadge status={event.decision} />}
            </div>
            {event.reason_code && <p className="text-sm text-slate-500">Reason: {event.reason_code}</p>}
            <p className="text-xs text-slate-400">{formatDate(event.created_at)}</p>
          </div>
        </li>
      ))}
    </ol>
  )
}
