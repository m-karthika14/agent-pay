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
}
