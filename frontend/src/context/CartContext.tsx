/**
 * Storefront cart state (plan.md Section 18 — mutable cart lifecycle).
 *
 * Scoped per-merchant: a user can have a separate OPEN cart at each
 * merchant (e.g. one at UrbanNest, one at TechHub), so both the
 * localStorage key and the server-side discovery call are keyed by the
 * current merchant, derived from the URL (every cart-aware page lives
 * under /store/:merchantSlug/...). The cart_id itself is persisted to
 * localStorage so it survives navigation and page reloads across
 * HomePage -> ProductPage -> CartPage. Cart creation is deferred until the
 * first addItem() call, since it needs a merchant_id (read off the product
 * being added) that isn't known any earlier.
 */
import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { useLocation } from 'react-router-dom'
import * as cartApi from '../services/cartApi'
import type { CartResponse } from '../types/cart'
import { useBuyer } from './BuyerContext'
import { merchantSlugFromPath } from '../lib/merchantRoute'

/** The localStorage key CartContext reads/writes a merchant's cart_id under -- exported so GlobalAuthorizationPopup's "Review" deep link can prime the exact same key before navigating. */
export function cartIdStorageKey(merchantSlug: string): string {
  return `agentpay_cart_id:${merchantSlug}`
}

interface CartContextValue {
  cart: CartResponse | null
  loading: boolean
  error: Error | null
  itemCount: number
  addItem: (productId: string, merchantId: string, quantity?: number) => Promise<void>
  updateItem: (itemId: string, quantity: number) => Promise<void>
  removeItem: (itemId: string) => Promise<void>
  clearCart: () => void
}

const CartContext = createContext<CartContextValue | null>(null)

/** Provides cart state and mutations to the storefront's component tree, scoped to the current /store/:merchantSlug route. */
export function CartProvider({ children }: { children: ReactNode }) {
  const { userId } = useBuyer()
  const location = useLocation()
  const merchantSlug = merchantSlugFromPath(location.pathname)
  const [cart, setCart] = useState<CartResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  useEffect(() => {
    if (!userId || !merchantSlug) {
      setCart(null)
      return
    }
    const storageKey = cartIdStorageKey(merchantSlug)
    const cartId = localStorage.getItem(storageKey)
    if (cartId) {
      setLoading(true)
      cartApi
        .getCart(cartId)
        .then((result) => setCart(result))
        .catch(() => {
          // The stored cart is gone or no longer usable (e.g. already frozen
          // by a completed checkout) -- drop it and let the next addItem()
          // start a fresh one.
          localStorage.removeItem(storageKey)
        })
        .finally(() => setLoading(false))
      return
    }
    // No cart_id known to this browser for this merchant yet -- check
    // whether this user already has an OPEN cart there from elsewhere
    // (e.g. one Claude created via MCP under the same user_id), so
    // visiting this merchant surfaces it automatically.
    setLoading(true)
    cartApi
      .getOpenCartForUser(userId, merchantSlug)
      .then((result) => {
        if (result) {
          localStorage.setItem(storageKey, result.cart_id)
          setCart(result)
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [userId, merchantSlug])

  const addItem = useCallback(
    async (productId: string, merchantId: string, quantity = 1) => {
      if (!userId) throw new Error('Buyer identity is not resolved yet.')
      if (!merchantSlug) throw new Error('Not currently shopping at a merchant.')
      setLoading(true)
      setError(null)
      try {
        const storageKey = cartIdStorageKey(merchantSlug)
        let cartId = localStorage.getItem(storageKey)
        if (!cartId) {
          const created = await cartApi.createCart(userId, merchantId)
          cartId = created.cart_id
          localStorage.setItem(storageKey, cartId)
        }
        const updated = await cartApi.addCartItem(cartId, productId, quantity)
        setCart(updated)
      } catch (err) {
        setError(err instanceof Error ? err : new Error(String(err)))
        throw err
      } finally {
        setLoading(false)
      }
    },
    [userId, merchantSlug],
  )

  const updateItem = useCallback(
    async (itemId: string, quantity: number) => {
      if (!merchantSlug) return
      const cartId = localStorage.getItem(cartIdStorageKey(merchantSlug))
      if (!cartId) return
      setLoading(true)
      setError(null)
      try {
        const updated = await cartApi.updateCartItem(cartId, itemId, quantity)
        setCart(updated)
      } catch (err) {
        setError(err instanceof Error ? err : new Error(String(err)))
        throw err
      } finally {
        setLoading(false)
      }
    },
    [merchantSlug],
  )

  const removeItem = useCallback(
    async (itemId: string) => {
      if (!merchantSlug) return
      const cartId = localStorage.getItem(cartIdStorageKey(merchantSlug))
      if (!cartId) return
      setLoading(true)
      setError(null)
      try {
        const updated = await cartApi.removeCartItem(cartId, itemId)
        setCart(updated)
      } catch (err) {
        setError(err instanceof Error ? err : new Error(String(err)))
        throw err
      } finally {
        setLoading(false)
      }
    },
    [merchantSlug],
  )

  const clearCart = useCallback(() => {
    if (merchantSlug) localStorage.removeItem(cartIdStorageKey(merchantSlug))
    setCart(null)
  }, [merchantSlug])

  const itemCount = cart?.items.reduce((sum, item) => sum + item.quantity, 0) ?? 0

  return (
    <CartContext.Provider value={{ cart, loading, error, itemCount, addItem, updateItem, removeItem, clearCart }}>
      {children}
    </CartContext.Provider>
  )
}

/** Read cart state and mutations. Must be used within a CartProvider. */
export function useCart(): CartContextValue {
  const ctx = useContext(CartContext)
  if (!ctx) throw new Error('useCart must be used within a CartProvider')
  return ctx
}
