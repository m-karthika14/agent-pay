/**
 * TypeScript shapes mirroring backend/app/schemas/audit.py -- kept
 * hand-in-sync rather than generated, since the backend is the single
 * source of truth (plan.md Section 20's "Every API function gets a
 * TypeScript doc comment" implies these types document the contract, not
 * redefine it).
 */

/** One tamper-evident, hash-chained audit log entry (plan.md Section 24 "Audit viewer"). */
export interface AuditEventRecord {
  event_id: string
  event_type: string
  actor_type: string
  payload_hash: string
  /** The exact payload the hash above was computed over -- null for events recorded before this field existed. */
  payload: Record<string, unknown> | null
  previous_hash: string | null
  event_hash: string
  decision: string | null
  reason_code: string | null
  mandate_id: string | null
  order_id: string | null
  /** Set on events that predate any mandate (CART_CREATED, AUTHORIZATION_*), so a buyer's own pre-mandate activity stays queryable. */
  user_id: string | null
  created_at: string | null
}

/** Describes the first point at which a hash-chain verification fails, if any. */
export interface ChainMismatch {
  event_id: string
  position: number
  reason: string
}

/** Result of verifying a sequence of audit events for tamper-evidence (plan.md Section 23.3). */
export interface ChainVerificationResult {
  valid: boolean
  events_checked: number
  first_mismatch: ChainMismatch | null
  verified_at: string
}
