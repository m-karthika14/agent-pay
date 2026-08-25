/**
 * API functions for resolving the storefront's demo buyer identity
 * (plan.md Section 19 — no real auth, email is the identity key).
 */
import { apiPost } from './apiClient'
import type { UserResponse } from '../types/user'

/** Resolve (or create, on first sight) a demo user by email. */
export function getOrCreateUser(email: string, name?: string): Promise<UserResponse> {
  return apiPost<UserResponse>('/api/users', name ? { email, name } : { email })
}
