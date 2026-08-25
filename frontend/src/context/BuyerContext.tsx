/**
 * Demo buyer identity for the storefront (plan.md Section 19 — no real
 * auth; email is the lightweight identity key). On first visit a random
 * demo email/name is generated and persisted to localStorage; on every
 * visit it's resolved to a real backend user_id via POST /api/users
 * (idempotent get-or-create), since carts require an existing User row.
 */
import { createContext, useContext, useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { getOrCreateUser } from '../services/userApi'

const EMAIL_KEY = 'agentpay_buyer_email'
const NAME_KEY = 'agentpay_buyer_name'
const DEFAULT_NAME = 'Storefront Buyer'

interface BuyerContextValue {
  userId: string | null
  email: string | null
  name: string
  loading: boolean
  error: Error | null
}

const BuyerContext = createContext<BuyerContextValue | null>(null)

function loadOrCreateIdentity(): { email: string; name: string } {
  let email = localStorage.getItem(EMAIL_KEY)
  let name = localStorage.getItem(NAME_KEY)
  if (!email) {
    email = `buyer-${Math.random().toString(36).slice(2, 10)}@urbannest.demo`
    localStorage.setItem(EMAIL_KEY, email)
  }
  if (!name) {
    name = DEFAULT_NAME
    localStorage.setItem(NAME_KEY, name)
  }
  return { email, name }
}

/** Provides the resolved demo buyer identity to the storefront's component tree. */
export function BuyerProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<Omit<BuyerContextValue, 'email' | 'name'> & { email: string; name: string }>(
    () => {
      const { email, name } = loadOrCreateIdentity()
      return { userId: null, email, name, loading: true, error: null }
    },
  )

  useEffect(() => {
    let cancelled = false
    getOrCreateUser(state.email, state.name)
      .then((user) => {
        if (!cancelled) setState((prev) => ({ ...prev, userId: user.user_id, loading: false }))
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setState((prev) => ({
            ...prev,
            loading: false,
            error: error instanceof Error ? error : new Error(String(error)),
          }))
        }
      })
    return () => {
      cancelled = true
    }
    // Runs once on mount: the demo identity is fixed for the browser session.
  }, [])

  return <BuyerContext.Provider value={state}>{children}</BuyerContext.Provider>
}

/** Read the resolved demo buyer identity. Must be used within a BuyerProvider. */
export function useBuyer(): BuyerContextValue {
  const ctx = useContext(BuyerContext)
  if (!ctx) throw new Error('useBuyer must be used within a BuyerProvider')
  return ctx
}
