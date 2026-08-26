/**
 * TypeScript shapes mirroring backend/app/schemas/product.py -- the
 * storefront's product catalog (plan.md Section 19.1).
 */

/** A single catalog product. */
export interface ProductResponse {
  product_id: string
  merchant_id: string
  merchant_name: string
  merchant_slug: string
  sku: string
  name: string
  description: string
  price_minor: number
  currency: string
  category: string
  availability: string
  delivery: string
  return_policy: string
}

/** Stock level for a single product. */
export interface InventoryResponse {
  product_id: string
  quantity: number
  reserved_quantity: number
  available_quantity: number
}
