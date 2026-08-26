/**
 * Buyer identity for the storefront (plan.md Section 19), backed by a real
 * login (POST /api/auth/login) rather than an auto-generated per-device
 * identity.
 *
 * Why this matters: Claude (via MCP) and the browser must resolve to the
 * exact same User row for a cart Claude creates to actually show up in the
 * browser's own cart page. The previous auto-generated-random-email
 * approach could never match whatever user_id a human had separately
 * handed to Claude in conversation -- logging in as that same email (or
 * claiming a password for a user_id Claude/MCP already created via
 * POST /api/users, see app.auth.service.login_or_claim) fixes that.
 */
import { createContext, useContext, useState } from 'react'
import type { ReactNode } from 'react'
import { login as loginRequest } from '../services/userApi'

const USER_ID_KEY = 'agentpay_buyer_user_id'
const EMAIL_KEY = 'agentpay_buyer_email'
const NAME_KEY = 'agentpay_buyer_name'
const CART_ID_KEY = 'agentpay_cart_id'

interface BuyerContextValue {
  userId: string | null
  email: string | null
  name: string | null
  loading: boolean
  error: Error | null
  login: (email: string, password: string, name?: string) => Promise<void>
  logout: () => void
}

const BuyerContext = createContext<BuyerContextValue | null>(null)

interface StoredIdentity {
  userId: string | null
  email: string | null
  name: string | null
}

function loadStoredIdentity(): StoredIdentity {
  return {
    userId: localStorage.getItem(USER_ID_KEY),
    email: localStorage.getItem(EMAIL_KEY),
    name: localStorage.getItem(NAME_KEY),
  }
}

/** Provides the logged-in buyer identity to the storefront's component tree. */
export function BuyerProvider({ children }: { children: ReactNode }) {
  const [identity, setIdentity] = useState<StoredIdentity>(loadStoredIdentity)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  async function login(email: string, password: string, name?: string): Promise<void> {
    setLoading(true)
    setError(null)
    try {
      const user = await loginRequest(email, password, name)
      localStorage.setItem(USER_ID_KEY, user.user_id)
      localStorage.setItem(EMAIL_KEY, user.email)
      localStorage.setItem(NAME_KEY, user.name)
      setIdentity({ userId: user.user_id, email: user.email, name: user.name })
    } catch (err) {
      const asError = err instanceof Error ? err : new Error(String(err))
      setError(asError)
      throw asError
    } finally {
      setLoading(false)
    }
  }

  function logout(): void {
    localStorage.removeItem(USER_ID_KEY)
    localStorage.removeItem(EMAIL_KEY)
    localStorage.removeItem(NAME_KEY)
    // The cart belongs to whichever user was logged in -- switching
    // identity must not let the next login silently pick up a stranger's
    // in-progress cart.
    localStorage.removeItem(CART_ID_KEY)
    window.location.href = '/login'
  }

  return (
    <BuyerContext.Provider value={{ ...identity, loading, error, login, logout }}>{children}</BuyerContext.Provider>
  )
}

/** Read the logged-in buyer identity. Must be used within a BuyerProvider. */
export function useBuyer(): BuyerContextValue {
  const ctx = useContext(BuyerContext)
  if (!ctx) throw new Error('useBuyer must be used within a BuyerProvider')
  return ctx
}
