/**
 * TypeScript shapes mirroring backend/app/schemas/budget.py -- a user's own,
 * independently-set "AI Shopping Budget" (plan.md Phase 4).
 */

/** A user's current AI Shopping Budget, or all-null fields if they've never set one (or it expired). */
export interface BudgetResponse {
  max_amount_minor: number | null
  allow_addons: boolean | null
  currency: string
  expires_at: string | null
  is_active: boolean
}

/** Request body for PUT /api/users/{user_id}/budget. */
export interface SetBudgetRequestBody {
  max_amount_minor: number
  allow_addons: boolean
  expires_in_hours: number
}
