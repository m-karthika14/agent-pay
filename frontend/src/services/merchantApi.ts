/**
 * API functions for the merchant picker (plan.md Section 18).
 */
import { apiGet } from './apiClient'
import type { MerchantResponse } from '../types/merchant'

/** List every AI-transactable demo merchant. */
export function listMerchants(): Promise<MerchantResponse[]> {
  return apiGet<MerchantResponse[]>('/api/merchants')
}
