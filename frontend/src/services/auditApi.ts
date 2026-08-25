/**
 * API functions for the hash-chained audit log (plan.md Section 18 — Audit).
 */
import { apiGet } from './apiClient'
import type { AuditEventRecord, ChainVerificationResult } from '../types/audit'

/** Fetch a transaction's own audit events, oldest first, with full hash-chain fields. */
export function getTransactionAuditEvents(transactionId: string): Promise<AuditEventRecord[]> {
  return apiGet<AuditEventRecord[]>(`/api/audit/${transactionId}`)
}

/**
 * Verify AgentPay's entire hash-chained audit log. The chain is global
 * (plan.md Section 23.2), so this checks the whole ledger, not just the
 * events belonging to `transactionId` -- see the backend route's docstring.
 */
export function verifyAuditChain(transactionId: string): Promise<ChainVerificationResult> {
  return apiGet<ChainVerificationResult>(`/api/audit/${transactionId}/verify`)
}
