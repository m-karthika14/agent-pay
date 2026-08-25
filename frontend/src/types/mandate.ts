/**
 * TypeScript shapes mirroring backend/app/schemas/mandate.py's REST-facing
 * request/response pair -- the storefront's "authorize a purchase" step
 * (plan.md Section 18 `POST /api/mandates`).
 */

/** A buyer's stated purchase intent/constraints, submitted to authorize a purchase. */
export interface CreateMandateRequest {
  user_email: string
  user_name?: string
  merchant_id: string
  currency?: string
  max_amount_minor: number
  allowed_categories: string[]
  allow_addons?: boolean
  delivery_requirement?: string
  single_use?: boolean
  expires_in_hours?: number
  product_type: string
  notes?: string | null
}

/** A mandate's public, decoded content -- includes the mandate_id to hand to Claude. */
export interface MandateResponse {
  mandate_id: string
  merchant_id: string
  currency: string
  max_amount_minor: number
  allowed_categories: string[]
  allow_addons: boolean
  delivery_requirement: string
  single_use: boolean
  expires_at: string
  product_type: string
  notes: string | null
  status: string
}

/** Deterministic outcome of verifying a signed mandate's signature and lifecycle state. */
export interface MandateVerificationResult {
  valid: boolean
  reason_code: string | null
  reason: string | null
}
