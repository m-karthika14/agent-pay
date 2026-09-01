/**
 * API functions for a user's own "Automatic Payments" authorization
 * (plan.md Phase 5) -- set on the landing page, beside the AI Shopping
 * Budget, and checked by the backend before it ever executes payment
 * without a manual "Pay" click.
 */
import { apiDelete, apiGet, apiPost } from './apiClient'
import type {
  ConfirmPaymentAuthorizationRequestBody,
  PaymentAuthorizationResponse,
  SetupPaymentAuthorizationRequestBody,
  SetupPaymentAuthorizationResponse,
} from '../types/paymentAuthorization'

/** Fetch a user's current Automatic Payments authorization (is_active=false if never set, revoked, or expired). */
export function getPaymentAuthorization(userId: string): Promise<PaymentAuthorizationResponse> {
  return apiGet<PaymentAuthorizationResponse>(`/api/users/${userId}/payment-authorization`)
}

/** Start the ONE interactive Razorpay Checkout step that registers a reusable payment token. */
export function setupPaymentAuthorization(
  userId: string,
  body: SetupPaymentAuthorizationRequestBody,
): Promise<SetupPaymentAuthorizationResponse> {
  return apiPost<SetupPaymentAuthorizationResponse>(`/api/users/${userId}/payment-authorization`, body)
}

/** Confirm the setup transaction actually succeeded (verified by the backend against Razorpay directly) and activate it. */
export function confirmPaymentAuthorization(
  userId: string,
  body: ConfirmPaymentAuthorizationRequestBody,
): Promise<PaymentAuthorizationResponse> {
  return apiPost<PaymentAuthorizationResponse>(`/api/users/${userId}/payment-authorization/confirm`, body)
}

/** Revoke a user's Automatic Payments authorization. AgentPay stops attempting automatic payment immediately. */
export function revokePaymentAuthorization(userId: string): Promise<PaymentAuthorizationResponse> {
  return apiDelete<PaymentAuthorizationResponse>(`/api/users/${userId}/payment-authorization`)
}
