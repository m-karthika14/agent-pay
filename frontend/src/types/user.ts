/**
 * TypeScript shapes mirroring backend/app/schemas/user.py -- the
 * storefront's buyer identity/login (plan.md Section 19).
 */

/** A demo user's identity. */
export interface UserResponse {
  user_id: string
  email: string
  name: string
}

/** Request body for POST /api/auth/login. */
export interface LoginRequest {
  email: string
  password: string
  name?: string
}
