/**
 * TypeScript shapes mirroring backend/app/schemas/checkout.py and the
 * checkout-completion slice of backend/app/schemas/payment.py.
 */
import type { CartResponse } from './cart'

/** What happened, if anything, to a Merchant Revenue Agent proposal during one checkout. */
export interface ProposalOutcome {
  status: string
  product_id: string | null
  quantity: number | null
  reason: string | null
  reason_code: string | null
  intent_confidence: number | null
}

/** Result of a successful request_checkout() call. */
export interface CheckoutResponse {
  cart: CartResponse
  frozen_hash: string
  frozen_at: string
  proposal: ProposalOutcome | null
}

/** Everything the frontend needs to open Razorpay Standard Checkout for a frozen cart. */
export interface CheckoutSessionResponse {
  order_id: string
  razorpay_order_id: string
  razorpay_key_id: string
  amount_minor: number
  currency: string
  /**
   * Set only when Automatic Payments (plan.md Phase 5) was attempted for
   * this order. null means "no active payment authorization, proceed with
   * the manual Razorpay Checkout exactly as before." "CAPTURED" means the
   * order is already genuinely paid -- never open Razorpay Checkout at all.
   * Any other value ("REQUIRES_AUTHENTICATION"/"FAILED"/"INVALID") means
   * automatic payment did not complete -- the manual flow is the safe
   * fallback, never a false success.
   */
  auto_payment_status: string | null
}
