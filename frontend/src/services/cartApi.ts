/**
 * API functions for the mutable cart lifecycle (plan.md Section 18 — Cart).
 */
import { apiDelete, apiGet, apiPatch, apiPost } from './apiClient'
import type { CartResponse } from '../types/cart'

/** Create a new, empty, OPEN cart for a user at a merchant. */
export function createCart(userId: string, merchantId: string, currency = 'INR'): Promise<CartResponse> {
  return apiPost<CartResponse>('/api/carts', { user_id: userId, merchant_id: merchantId, currency })
}

/** Fetch a cart with its current line items. */
export function getCart(cartId: string): Promise<CartResponse> {
  return apiGet<CartResponse>(`/api/carts/${cartId}`)
}

/** Fetch the cart currently linked to a mandate, or null if none has been frozen under it yet. */
export function getCartByMandate(mandateId: string): Promise<CartResponse | null> {
  return apiGet<CartResponse | null>(`/api/carts/by-mandate/${mandateId}`)
}

/**
 * Fetch a user's current OPEN cart, or null if they have none -- how the
 * browser discovers a cart Claude created via MCP under the same user_id.
 * Pass `merchantSlug` to scope to that merchant's cart only -- a user can
 * have a separate OPEN cart at each merchant.
 */
export function getOpenCartForUser(userId: string, merchantSlug?: string): Promise<CartResponse | null> {
  const path = `/api/carts/by-user/${userId}`
  return apiGet<CartResponse | null>(merchantSlug ? `${path}?merchant=${encodeURIComponent(merchantSlug)}` : path)
}

/** Add a product to an OPEN cart (merges into an existing line if already present). */
export function addCartItem(cartId: string, productId: string, quantity: number): Promise<CartResponse> {
  return apiPost<CartResponse>(`/api/carts/${cartId}/items`, { product_id: productId, quantity })
}

/** Change a line item's quantity in an OPEN cart. */
export function updateCartItem(cartId: string, itemId: string, quantity: number): Promise<CartResponse> {
  return apiPatch<CartResponse>(`/api/carts/${cartId}/items/${itemId}`, { quantity })
}

/** Remove a line item from an OPEN cart. */
export function removeCartItem(cartId: string, itemId: string): Promise<CartResponse> {
  return apiDelete<CartResponse>(`/api/carts/${cartId}/items/${itemId}`)
}
