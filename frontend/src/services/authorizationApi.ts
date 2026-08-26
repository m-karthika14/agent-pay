/**
 * API functions for the Claude-initiated authorization-request flow
 * (plan.md Phase 2 -- the storefront's global "Claude wants to buy" popup).
 */
import { apiGet, apiPost } from './apiClient'
import type { ApproveAuthorizationRequestBody, AuthorizationRequestResponse } from '../types/authorization'

/** List every PENDING authorization request across a user's carts. Polled by the global popup. */
export function listPendingAuthorizationRequests(userId: string): Promise<AuthorizationRequestResponse[]> {
  return apiGet<AuthorizationRequestResponse[]>(`/api/authorization-requests/by-user/${userId}`)
}

/** Approve a PENDING request, signing a real mandate from `terms` -- the human's (possibly edited) terms. */
export function approveAuthorizationRequest(
  requestId: string,
  terms: ApproveAuthorizationRequestBody,
): Promise<AuthorizationRequestResponse> {
  return apiPost<AuthorizationRequestResponse>(`/api/authorization-requests/${requestId}/approve`, terms)
}

/** Reject a PENDING request. No mandate is created. */
export function rejectAuthorizationRequest(requestId: string): Promise<AuthorizationRequestResponse> {
  return apiPost<AuthorizationRequestResponse>(`/api/authorization-requests/${requestId}/reject`)
}
