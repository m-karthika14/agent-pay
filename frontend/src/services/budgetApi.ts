/**
 * API functions for a user's own "AI Shopping Budget" (plan.md Phase 4) --
 * the independent spending ceiling set on the landing page, below "Logged
 * in as ...", checked by the backend before Claude may ever request more.
 */
import { apiGet, apiPut } from './apiClient'
import type { BudgetResponse, SetBudgetRequestBody } from '../types/budget'

/** Fetch a user's current AI Shopping Budget (all-null/is_active=false if never set or expired). */
export function getBudget(userId: string): Promise<BudgetResponse> {
  return apiGet<BudgetResponse>(`/api/users/${userId}/budget`)
}

/** Set (replacing any prior) AI Shopping Budget for this user. */
export function setBudget(userId: string, body: SetBudgetRequestBody): Promise<BudgetResponse> {
  return apiPut<BudgetResponse>(`/api/users/${userId}/budget`, body)
}
