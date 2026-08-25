import { useAsync } from './useAsync'
import { getTransactionTrace } from '../services/transactionApi'
import type { TransactionTraceResponse } from '../types/transaction'

/** Fetches a transaction's full trace (order, cart, mandate, buyer, events) and exposes loading/error state. */
export function useTransaction(transactionId: string) {
  return useAsync<TransactionTraceResponse>(() => getTransactionTrace(transactionId), [transactionId])
}
