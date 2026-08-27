import { useMemo } from 'react'
import { usePolling } from './usePolling'
import { getMandateAuditEvents, getUserAuditEvents } from '../services/auditApi'
import { getCart } from '../services/cartApi'
import type { AuditEventRecord } from '../types/audit'
import type { CartResponse } from '../types/cart'

interface LiveShoppingActivity {
  events: AuditEventRecord[]
  cart: CartResponse | null
}

function payloadString(event: AuditEventRecord, key: string): string | null {
  const value = event.payload?.[key]
  return typeof value === 'string' ? value : null
}

/**
 * This user's most recent CART_CREATED event, if any -- "start a new
 * shopping session" always produces a fresh one of these, so it's also
 * used as the cutoff for scoping search/view activity to the CURRENT
 * session (see scopedUserEvents below).
 */
function latestCartCreated(userEvents: AuditEventRecord[]): { cartId: string; createdAt: string } | null {
  let latest: { cartId: string; createdAt: string } | null = null
  for (const event of userEvents) {
    if (event.event_type !== 'CART_CREATED') continue
    const cartId = payloadString(event, 'cart_id')
    const createdAt = event.created_at ?? ''
    if (!cartId) continue
    if (!latest || createdAt > latest.createdAt) latest = { cartId, createdAt }
  }
  return latest
}

/** The mandate_id an APPROVED authorization request for this exact cart produced, if any. */
function approvedMandateIdForCart(userEvents: AuditEventRecord[], cartId: string): string | null {
  for (const event of userEvents) {
    if (event.event_type !== 'AUTHORIZATION_APPROVED') continue
    if (payloadString(event, 'cart_id') !== cartId) continue
    const mandateId = payloadString(event, 'mandate_id')
    if (mandateId) return mandateId
  }
  return null
}

/**
 * Live activity for the logged-in buyer's most recent cart, merging their
 * own pre-mandate events (CART_CREATED, AUTHORIZATION_*) with the
 * mandate-onward ones (HARD_POLICY_PASSED, CART_FROZEN, MERCHANT_AGENT_*,
 * INTENT_GATE_*, RAZORPAY_*...) once an authorization is approved --
 * feeding the global live-activity popup (plan.md "watch Claude shop, no
 * mandate_id to paste in").
 *
 * Scoped to the most recent cart, not every cart this user has ever had --
 * otherwise a second shopping session would keep piling its events onto the
 * first one's conversation forever.
 */
export function useLiveShoppingActivity(userId: string | null): LiveShoppingActivity {
  const userActivity = usePolling(() => getUserAuditEvents(userId as string), [userId], {
    enabled: !!userId,
    intervalMs: 3000,
  })

  const currentCart = userActivity.data ? latestCartCreated(userActivity.data) : null
  const cartId = currentCart?.cartId ?? null
  const mandateId = cartId && userActivity.data ? approvedMandateIdForCart(userActivity.data, cartId) : null

  const scopedUserEvents = useMemo(() => {
    if (!userActivity.data) return []
    // Before any cart exists yet, there's nothing to disambiguate a
    // "session" from -- show every pre-cart search/view event as-is.
    // Once a cart exists, only events from that cart's own creation
    // onward count as the CURRENT session -- otherwise a second "start a
    // new shopping session" would just keep piling onto the first one's
    // conversation forever instead of replacing it.
    if (!currentCart) return userActivity.data
    return userActivity.data.filter((e) => (e.created_at ?? '') >= currentCart.createdAt)
  }, [userActivity.data, currentCart])

  const mandateActivity = usePolling(() => getMandateAuditEvents(mandateId as string), [mandateId], {
    enabled: !!mandateId,
    intervalMs: 3000,
  })
  const cartPoll = usePolling(() => getCart(cartId as string), [cartId], { enabled: !!cartId, intervalMs: 5000 })

  const events = useMemo(() => {
    // AUTHORIZATION_APPROVED carries both user_id and mandate_id, so it
    // matches both queries -- dedupe by event_id before merging, or it
    // would render as two identical bubbles.
    const byId = new Map<string, AuditEventRecord>()
    for (const event of [...scopedUserEvents, ...(mandateActivity.data ?? [])]) byId.set(event.event_id, event)
    return Array.from(byId.values()).sort((a, b) => (a.created_at ?? '').localeCompare(b.created_at ?? ''))
  }, [scopedUserEvents, mandateActivity.data])

  return { events, cart: cartPoll.data }
}
