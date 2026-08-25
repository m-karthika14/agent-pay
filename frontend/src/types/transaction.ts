/**
 * TypeScript shapes mirroring backend/app/schemas/payment.py -- the
 * Merchant Console's Transaction view (plan.md Section 19.2/24).
 */
import type { CartResponse } from './cart'

/** A single payment transaction against an order. */
export interface TransactionResponse {
  transaction_id: string
  order_id: string
  razorpay_payment_id: string | null
  status: string
  failure_code: string | null
  failure_message: string | null
  created_at: string
  updated_at: string
}

/** One audit event in a transaction's decision trace (plan.md Section 24 "Decision trace"). */
export interface TransactionTraceEvent {
  event_type: string
  decision: string | null
  reason_code: string | null
  created_at: string
}

/** The order linking a transaction back to its authorizing cart and mandate. */
export interface OrderSummary {
  order_id: string
  cart_id: string
  mandate_id: string
  razorpay_order_id: string | null
  status: string
  amount_minor: number
  currency: string
}

/** The signed mandate that authorized a transaction (decoded, not the raw signature). */
export interface MandateSummary {
  mandate_id: string
  product_type: string
  notes: string | null
  max_amount_minor: number
  allowed_categories: string[]
  status: string
}

/** The buyer who authorized a transaction. */
export interface BuyerSummary {
  user_id: string
  email: string
  name: string
}

/** A transaction's full trace: order, cart, mandate, buyer, and the ordered decision events. */
export interface TransactionTraceResponse {
  transaction: TransactionResponse
  order: OrderSummary
  cart: CartResponse
  mandate: MandateSummary
  buyer: BuyerSummary
  events: TransactionTraceEvent[]
}
