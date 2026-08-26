/**
 * API functions for the storefront's buyer identity/login
 * (plan.md Section 19).
 */
import { apiPost } from './apiClient'
import type { UserResponse } from '../types/user'

/** Resolve (or create, on first sight) a demo user by email -- no password, still used by Claude/MCP. */
export function getOrCreateUser(email: string, name?: string): Promise<UserResponse> {
  return apiPost<UserResponse>('/api/users', name ? { email, name } : { email })
}

/** Log in by email + password -- or sign up / claim a password-less account on first login. */
export function login(email: string, password: string, name?: string): Promise<UserResponse> {
  return apiPost<UserResponse>('/api/auth/login', name ? { email, password, name } : { email, password })
}
