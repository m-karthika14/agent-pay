import { formatDate } from '../lib/formatDate'
import { StatusBadge } from './StatusBadge'
import type { AuditEventRecord } from '../types/audit'

interface EventFeedProps {
  events: AuditEventRecord[]
}

/**
 * A live-feed-style list of recent audit events, newest first (Merchant
 * Console overview panel, plan.md Section 19.2 "Current agent session").
 */
export function EventFeed({ events }: EventFeedProps) {
  if (events.length === 0) {
    return <p className="text-sm text-slate-500">No audit events yet.</p>
  }
  return (
    <ul className="divide-y divide-slate-100">
      {events.map((event) => (
        <li key={event.event_id} className="flex items-center justify-between py-2 text-sm">
          <div>
            <p className="font-medium text-slate-800">{event.event_type}</p>
            <p className="text-xs text-slate-400">{event.created_at ? formatDate(event.created_at) : '—'}</p>
          </div>
          {event.decision && <StatusBadge status={event.decision} />}
        </li>
      ))}
    </ul>
  )
}
