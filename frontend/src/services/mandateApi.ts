/**
 * API functions for creating and inspecting mandates (plan.md Section 18 — Mandate).
 */
import { apiGet, apiPost } from './apiClient'
import type { CreateMandateRequest, MandateResponse, MandateVerificationResult } from '../types/mandate'

/** Sign and persist a new mandate from a buyer's stated intent, returning its mandate_id. */
export function createMandate(request: CreateMandateRequest): Promise<MandateResponse> {
  return apiPost<MandateResponse>('/api/mandates', request)
}

/** List every mandate a user has ever authorized, newest first. */
export function listMandatesForUser(userId: string): Promise<MandateResponse[]> {
  return apiGet<MandateResponse[]>(`/api/mandates/by-user/${userId}`)
}

/** Fetch a mandate's public, decoded content by its business-facing mandate_id. */
export function getMandate(mandateId: string): Promise<MandateResponse> {
  return apiGet<MandateResponse>(`/api/mandates/${mandateId}`)
}

/** Verify a mandate's signature and lifecycle state. */
export function verifyMandate(mandateId: string): Promise<MandateVerificationResult> {
  return apiPost<MandateVerificationResult>(`/api/mandates/${mandateId}/verify`)
}
