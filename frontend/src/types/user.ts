/**
 * TypeScript shape mirroring backend/app/schemas/user.py -- the storefront's
 * lightweight, no-real-auth demo identity (plan.md Section 19).
 */

/** A demo user's identity. */
export interface UserResponse {
  user_id: string
  email: string
  name: string
}
