import { Link } from 'react-router-dom'
import { EventFeed } from '../components/EventFeed'
import { MetricCard } from '../components/MetricCard'
import { StatusBadge } from '../components/StatusBadge'
import { useConsoleEvents, useConsoleSummary } from '../hooks/useConsole'
// import { useConsoleMetrics } from '../hooks/useConsole' -- unused while the Evaluation section below is commented out
import { formatCurrency } from '../lib/formatCurrency'
import { formatDate } from '../lib/formatDate'
import { getMerchantTheme } from '../lib/merchantTheme'

/**
 * The Merchant Console's overview page (plan.md Section 19.2): aggregate
 * basket/transaction metrics, the Phase 10 evaluation result if available,
 * recent transactions, and a live audit event feed.
 */
export function MerchantConsolePage() {
  const summary = useConsoleSummary()
  // const metrics = useConsoleMetrics()
  const events = useConsoleEvents(15)

  return (
    <div className="space-y-8">
      <section>
        <h2 className="mb-3 text-sm font-semibold text-slate-700">Overview</h2>
        {summary.loading && <p className="text-sm text-slate-500">Loading…</p>}
        {summary.error && <p className="text-sm text-red-600">{summary.error.message}</p>}
        {summary.data && (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <MetricCard label="Transactions" value={String(summary.data.total_transactions)} />
            <MetricCard label="Mandates issued" value={String(summary.data.total_mandates)} />
            <MetricCard label="Audit events" value={String(summary.data.total_audit_events)} />
            {Object.entries(summary.data.transaction_count_by_status).map(([status, count]) => (
              <MetricCard key={status} label={status} value={String(count)} />
            ))}
          </div>
        )}
      </section>

      {/*
      <section>
        <h2 className="mb-3 text-sm font-semibold text-slate-700">Evaluation (Phase 10)</h2>
        {metrics.loading && <p className="text-sm text-slate-500">Loading…</p>}
        {metrics.data && !metrics.data.available && (
          <p className="text-sm text-slate-500">
            No evaluation report yet — run <code className="font-mono">uv run python eval/metrics.py</code>.
          </p>
        )}
        {metrics.data?.available && metrics.data.metrics && <MetricsSummary metrics={metrics.data.metrics} />}
      </section>
      */}

      <section>
        <h2 className="mb-3 text-sm font-semibold text-slate-700">Recent Transactions</h2>
        {summary.data && summary.data.recent_transactions.length === 0 && (
          <p className="text-sm text-slate-500">No transactions yet.</p>
        )}
        {summary.data && summary.data.recent_transactions.length > 0 && (
          <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
            <ul className="divide-y divide-slate-100">
              {summary.data.recent_transactions.map((row) => {
                const theme = getMerchantTheme(row.merchant_slug)
                return (
                  <li key={row.transaction_id}>
                    <Link
                      to={`/console/transactions/${row.transaction_id}`}
                      className="flex items-center justify-between px-4 py-3 text-sm hover:bg-slate-50"
                    >
                      <div>
                        <div className="flex items-center gap-2">
                          <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium text-white ${theme.primaryButton}`}>
                            {row.merchant_name}
                          </span>
                          <p className="font-mono text-xs text-slate-500">{row.transaction_id}</p>
                        </div>
                        <p className="mt-1 text-xs text-slate-400">{formatDate(row.created_at)}</p>
                      </div>
                      <div className="flex items-center gap-3">
                        <span className="font-medium text-slate-800">{formatCurrency(row.amount_minor, row.currency)}</span>
                        <StatusBadge status={row.status} />
                      </div>
                    </Link>
                  </li>
                )
              })}
            </ul>
          </div>
        )}
      </section>

      <section>
        <h2 className="mb-3 text-sm font-semibold text-slate-700">Live Event Feed</h2>
        {events.loading && <p className="text-sm text-slate-500">Loading…</p>}
        {events.data && (
          <div className="rounded-lg border border-slate-200 bg-white px-4">
            <EventFeed events={events.data} />
          </div>
        )}
      </section>
    </div>
  )
}

/*
 * Renders the Cap-only vs Intent-aware ceiling-drift comparison from
 * eval/metrics.py's report (plan.md Section 30 Slide 7). `metrics` is a
 * plain, loosely-typed object (see ConsoleMetricsResponse's docstring), so
 * field access here is defensive rather than assuming an exact shape.
 *
 * Commented out along with the "Evaluation (Phase 10)" section above.
 *
function MetricsSummary({ metrics }: { metrics: Record<string, unknown> }) {
  const ceilingDrift = metrics.ceiling_drift as
    | { cap_only?: { mean_drift?: number | null }; intent_aware?: { mean_drift?: number | null } }
    | undefined
  const violationsCaught = metrics.violations_caught as number | undefined
  const violationsAttempted = metrics.violations_attempted as number | undefined

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
      <MetricCard
        label="Ceiling Drift — Cap-only"
        value={ceilingDrift?.cap_only?.mean_drift != null ? ceilingDrift.cap_only.mean_drift.toFixed(3) : '—'}
      />
      <MetricCard
        label="Ceiling Drift — Intent-aware"
        value={ceilingDrift?.intent_aware?.mean_drift != null ? ceilingDrift.intent_aware.mean_drift.toFixed(3) : '—'}
      />
      <MetricCard
        label="Adversarial suite"
        value={violationsCaught != null && violationsAttempted != null ? `${violationsCaught}/${violationsAttempted}` : '—'}
        hint="violations caught / attempted"
      />
    </div>
  )
}
*/
