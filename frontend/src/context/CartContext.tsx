/**
 * Storefront cart state (plan.md Section 18 — mutable cart lifecycle).
 *
 * The cart_id is persisted to localStorage so it survives navigation and
 * page reloads across HomePage -> ProductPage -> CartPage. Cart creation is
 * deferred until the first addItem() call, since it needs a merchant_id
 * (read off the product being added) that isn't known any earlier.
 */
import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import * as cartApi from '../services/cartApi'
import type { CartResponse } from '../types/cart'
import { useBuyer } from './BuyerContext'

const CART_ID_KEY = 'agentpay_cart_id'

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

/** Provides cart state and mutations to the storefront's component tree. */
export function CartProvider({ children }: { children: ReactNode }) {
  const { userId } = useBuyer()
  const [cart, setCart] = useState<CartResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  useEffect(() => {
    const cartId = localStorage.getItem(CART_ID_KEY)
    if (!cartId) return
    setLoading(true)
    cartApi
      .getCart(cartId)
      .then((result) => setCart(result))
      .catch(() => {
        // The stored cart is gone or no longer usable (e.g. already frozen
        // by a completed checkout) -- drop it and let the next addItem()
        // start a fresh one.
        localStorage.removeItem(CART_ID_KEY)
      })
      .finally(() => setLoading(false))
  }, [])

  const addItem = useCallback(
    async (productId: string, merchantId: string, quantity = 1) => {
      if (!userId) throw new Error('Buyer identity is not resolved yet.')
      setLoading(true)
      setError(null)
      try {
        let cartId = localStorage.getItem(CART_ID_KEY)
        if (!cartId) {
          const created = await cartApi.createCart(userId, merchantId)
          cartId = created.cart_id
          localStorage.setItem(CART_ID_KEY, cartId)
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
    [userId],
  )

  const updateItem = useCallback(async (itemId: string, quantity: number) => {
    const cartId = localStorage.getItem(CART_ID_KEY)
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
  }, [])

  const removeItem = useCallback(async (itemId: string) => {
    const cartId = localStorage.getItem(CART_ID_KEY)
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
  }, [])

  const clearCart = useCallback(() => {
    localStorage.removeItem(CART_ID_KEY)
    setCart(null)
  }, [])

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
