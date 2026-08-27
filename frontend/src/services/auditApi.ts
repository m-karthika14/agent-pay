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
 * Fetch a mandate's audit events, oldest first -- works from mandate
 * creation onward, unlike getTransactionAuditEvents which needs an Order to
 * already exist. Polled by the "AI Activity" panel to show progress before
 * a transaction/order exists yet.
 */
export function getMandateAuditEvents(mandateId: string): Promise<AuditEventRecord[]> {
  return apiGet<AuditEventRecord[]>(`/api/audit/by-mandate/${mandateId}`)
}

/**
 * Fetch a buyer's own pre-mandate audit events (CART_CREATED,
 * AUTHORIZATION_REQUESTED/APPROVED/REJECTED), oldest first -- the events
 * getMandateAuditEvents can never see, since none of them carry a
 * mandate_id yet. Polled by the global live-activity popup so a buyer sees
 * Claude's shopping session automatically, with no mandate_id to paste in.
 */
export function getUserAuditEvents(userId: string): Promise<AuditEventRecord[]> {
  return apiGet<AuditEventRecord[]>(`/api/audit/by-user/${userId}`)
}

/**
 * Verify AgentPay's entire hash-chained audit log. The chain is global
 * (plan.md Section 23.2), so this checks the whole ledger, not just the
 * events belonging to `transactionId` -- see the backend route's docstring.
 */
export function verifyAuditChain(transactionId: string): Promise<ChainVerificationResult> {
  return apiGet<ChainVerificationResult>(`/api/audit/${transactionId}/verify`)
}
