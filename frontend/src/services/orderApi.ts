/**
 * API functions for buyer order history and payment-status sync
 * (plan.md Section 18/19 -- storefront "Buying History").
 */
import { apiGet, apiPost } from './apiClient'
import type { OrderHistoryEntry, OrderSummary } from '../types/transaction'

/** List every order a user has ever placed, newest first. */
export function getOrderHistory(userId: string): Promise<OrderHistoryEntry[]> {
  return apiGet<OrderHistoryEntry[]>(`/api/orders/by-user/${userId}`)
}

/**
 * Re-check an order's payment status directly against Razorpay and correct
 * AgentPay's stored state if a webhook delivery was missed -- e.g. no
 * public tunnel configured for a local backend to receive it.
 */
export function syncOrder(orderId: string): Promise<OrderSummary> {
  return apiPost<OrderSummary>(`/api/orders/${orderId}/sync`)
}
