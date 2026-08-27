/**
 * TypeScript shapes mirroring backend/app/schemas/cart.py.
 */

/** A single line item within a cart. */
export interface CartItemResponse {
  item_id: string
  product_id: string
  product_name: string
  category: string
  quantity: number
  unit_price_minor: number
  line_total_minor: number
}

/** A full cart with its line items, as returned by the checkout/transaction APIs. */
export interface CartResponse {
  cart_id: string
  user_id: string
  merchant_id: string
  status: string
  currency: string
  subtotal_minor: number
  frozen_at: string | null
  frozen_hash: string | null
  /** Business-facing mandate_id (e.g. "M-001") that froze this cart, if any. */
  mandate_id: string | null
  items: CartItemResponse[]
}
