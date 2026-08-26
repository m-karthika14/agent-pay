/**
 * TypeScript shapes mirroring backend/app/schemas/authorization.py -- the
 * Claude-initiated authorization-request flow (plan.md Phase 2).
 */

/** The (possibly human-edited) terms submitted to approve a request -- exactly what gets signed into the resulting mandate. */
export interface ApproveAuthorizationRequestBody {
  product_type: string
  max_amount_minor: number
  allowed_categories: string[]
  allow_addons: boolean
  delivery_requirement: string
  single_use: boolean
  expires_in_hours: number
  notes: string | null
}

/** An authorization request's public content, as shown in the storefront's global popup. */
export interface AuthorizationRequestResponse {
  request_id: string
  cart_id: string
  status: 'PENDING' | 'APPROVED' | 'REJECTED'
  product_type: string
  max_amount_minor: number
  allowed_categories: string[]
  allow_addons: boolean
  delivery_requirement: string
  single_use: boolean
  expires_in_hours: number
  notes: string | null
  reason: string | null
  resulting_mandate_id: string | null
  created_at: string
  decided_at: string | null
}
