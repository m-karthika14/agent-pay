import { formatDate } from '../lib/formatDate'
import { StatusBadge } from './StatusBadge'
import type { AuditEventRecord } from '../types/audit'

interface AuditTimelineProps {
  events: AuditEventRecord[]
}

/**
 * The full hash-chained audit timeline for one transaction (plan.md
 * Section 24 "Audit viewer": event, timestamp, decision, reason,
 * previous_hash, current_hash) -- unlike DecisionTrace, this shows the raw
 * chain-integrity fields judges can inspect directly.
 */
export function AuditTimeline({ events }: AuditTimelineProps) {
  if (events.length === 0) {
    return <p className="text-sm text-slate-500">No audit events recorded.</p>
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[640px] text-left text-sm">
        <thead>
          <tr className="border-b border-slate-200 text-xs tracking-wide text-slate-500 uppercase">
            <th className="py-2 pr-4">Event</th>
            <th className="py-2 pr-4">Timestamp</th>
            <th className="py-2 pr-4">Decision</th>
            <th className="py-2 pr-4">Reason</th>
            <th className="py-2 pr-4">Previous Hash</th>
            <th className="py-2">Event Hash</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {events.map((event) => (
            <tr key={event.event_id}>
              <td className="py-2 pr-4 font-medium text-slate-800">{event.event_type}</td>
              <td className="py-2 pr-4 text-slate-500">{event.created_at ? formatDate(event.created_at) : '—'}</td>
              <td className="py-2 pr-4">{event.decision && <StatusBadge status={event.decision} />}</td>
              <td className="py-2 pr-4 text-slate-500">{event.reason_code ?? '—'}</td>
              <td className="py-2 pr-4 font-mono text-xs text-slate-400" title={event.previous_hash ?? undefined}>
                {event.previous_hash ? `${event.previous_hash.slice(0, 10)}…` : '(genesis)'}
              </td>
              <td className="py-2 font-mono text-xs text-slate-400" title={event.event_hash}>
                {event.event_hash.slice(0, 10)}…
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
