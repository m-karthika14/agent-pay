/**
 * TypeScript shapes mirroring backend/app/schemas/console.py -- the
 * Merchant Console's overview panel (plan.md Section 19.2 "Revenue at
 * risk / basket metrics").
 */

/** One row in the console's recent-activity list. */
export interface RecentTransactionSummary {
  transaction_id: string
  order_id: string
  status: string
  amount_minor: number
  currency: string
  created_at: string
}

/** Merchant-wide aggregate counts. */
export interface ConsoleSummaryResponse {
  total_transactions: number
  transaction_count_by_status: Record<string, number>
  total_mandates: number
  total_audit_events: number
  recent_transactions: RecentTransactionSummary[]
}

/**
 * The Phase 10 evaluation report, if eval/metrics.py has been run.
 * `metrics` is untyped on purpose -- its shape comes from eval/metrics.py's
 * JSON output (ceiling_drift, abandonment, escalation, violations_caught,
 * ...), which is Python-side evaluation output, not a backend API contract.
 */
export interface ConsoleMetricsResponse {
  available: boolean
  metrics: Record<string, unknown> | null
}
