import { useAsync } from './useAsync'
import { listMerchants } from '../services/merchantApi'
import type { MerchantResponse } from '../types/merchant'

/** Fetch every AI-transactable demo merchant (the landing page's picker, and anywhere else that needs a merchant's display name). */
export function useMerchants() {
  return useAsync<MerchantResponse[]>(() => listMerchants(), [])
}
