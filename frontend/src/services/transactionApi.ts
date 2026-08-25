/**
 * API functions for fetching transaction detail/trace data
 * (plan.md Section 18 — Transactions).
 */
import { apiGet } from './apiClient'
import type { TransactionTraceResponse } from '../types/transaction'

/** Fetch a transaction's full trace (order, cart, mandate, buyer, decision events). */
export function getTransactionTrace(transactionId: string): Promise<TransactionTraceResponse> {
  return apiGet<TransactionTraceResponse>(`/api/transactions/${transactionId}/trace`)
}
