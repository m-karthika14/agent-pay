/**
 * API functions for the storefront's product catalog (plan.md Section 18 — Products).
 */
import { apiGet } from './apiClient'
import type { InventoryResponse, ProductResponse } from '../types/product'

/** List active products -- every demo merchant's, or just one (by slug) if given. */
export function listProducts(merchantSlug?: string): Promise<ProductResponse[]> {
  return apiGet<ProductResponse[]>(merchantSlug ? `/api/products?merchant=${encodeURIComponent(merchantSlug)}` : '/api/products')
}

/** Fetch a single product by id. */
export function getProduct(productId: string): Promise<ProductResponse> {
  return apiGet<ProductResponse>(`/api/products/${productId}`)
}

/** Fetch current stock level for a product. */
export function getProductInventory(productId: string): Promise<InventoryResponse> {
  return apiGet<InventoryResponse>(`/api/products/${productId}/inventory`)
}
