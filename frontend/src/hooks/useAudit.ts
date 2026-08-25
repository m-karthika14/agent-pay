import { useAsync } from './useAsync'
import { getTransactionAuditEvents, verifyAuditChain } from '../services/auditApi'
import type { AuditEventRecord, ChainVerificationResult } from '../types/audit'

/** Fetches a transaction's own audit events (oldest first) and exposes loading/error state. */
export function useAuditEvents(transactionId: string) {
  return useAsync<AuditEventRecord[]>(() => getTransactionAuditEvents(transactionId), [transactionId])
}

/** Verifies the (global) audit chain's integrity and exposes loading/error state. */
export function useAuditVerification(transactionId: string) {
  return useAsync<ChainVerificationResult>(() => verifyAuditChain(transactionId), [transactionId])
}
