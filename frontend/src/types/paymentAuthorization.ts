/**
 * TypeScript shapes mirroring backend/app/schemas/payment_authorization.py --
 * a user's own "Automatic Payments" authorization (plan.md Phase 5),
 * deliberately separate from the AI Shopping Budget (types/budget.ts).
 */

/** A user's current Automatic Payments authorization. */
export interface PaymentAuthorizationResponse {
  is_active: boolean
  status: string | null
  provider: string | null
  currency: string | null
  max_amount_minor: number | null
  authorized_at: string | null
  expires_at: string | null
}

/** Request body to start the ONE interactive Razorpay Checkout setup step. */
export interface SetupPaymentAuthorizationRequestBody {
  max_amount_minor: number
  currency: string
}

/** Everything needed to open Razorpay Checkout for the setup transaction. */
export interface SetupPaymentAuthorizationResponse {
  razorpay_order_id: string
  razorpay_key_id: string
  razorpay_customer_id: string
  amount_minor: number
  currency: string
}

/** Request body to confirm the setup transaction actually succeeded. */
export interface ConfirmPaymentAuthorizationRequestBody {
  razorpay_order_id: string
  razorpay_payment_id: string
}
