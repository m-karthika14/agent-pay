/**
 * TypeScript shape mirroring backend/app/schemas/merchant.py -- the
 * storefront's merchant picker (plan.md Section 18).
 */

/** One merchant a buyer (or buyer agent) can shop at. */
export interface MerchantResponse {
  merchant_id: string
  slug: string
  name: string
  currency: string
}
