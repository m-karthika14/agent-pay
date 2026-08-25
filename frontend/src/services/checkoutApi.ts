/**
 * API functions for the checkout boundary and Razorpay session creation
 * (plan.md Section 18 — Checkout).
 */
import { apiPost } from './apiClient'
import type { CheckoutResponse, CheckoutSessionResponse } from '../types/checkout'

/** Run AgentPay's deterministic checkout boundary against a cart, freezing it if every hard check passes. */
export function requestCheckout(cartId: string, mandateId: string): Promise<CheckoutResponse> {
  return apiPost<CheckoutResponse>('/api/checkout/request', { cart_id: cartId, mandate_id: mandateId })
}

/** Create (or idempotently re-return) a Razorpay Test Mode order for a frozen cart. */
export function completePurchase(cartId: string, mandateId: string): Promise<CheckoutSessionResponse> {
  return apiPost<CheckoutSessionResponse>(`/api/checkout/${cartId}/complete`, { mandate_id: mandateId })
}
