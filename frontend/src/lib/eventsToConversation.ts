/**
 * Turns AgentPay's real audit events into a WhatsApp-style conversation
 * between the three actors (Claude, the Merchant Revenue Agent, AgentPay).
 *
 * Every message either comes directly from an audit event AgentPay actually
 * recorded (event_type/decision/reason_code/payload -- the payload is real,
 * persisted data, see backend/app/db/models/audit_event.py's payload_json),
 * or, for Claude's single opening line, is a plain-language rendering of
 * the cart's real, already-fetched contents. Nothing here is invented,
 * randomized, or animated for effect -- this module only translates
 * already-true facts into sentences.
 */
import { formatCurrency } from './formatCurrency'
import type { AuditEventRecord } from '../types/audit'
import type { CartResponse } from '../types/cart'

export type ConversationActor = 'claude' | 'merchant' | 'agentpay'
export type ConversationTone = 'neutral' | 'pass' | 'blocked' | 'approved' | 'checking'

export interface ConversationEvidence {
  mandate?: { maxAmountMinor?: number; allowedCategories?: string[]; allowAddons?: boolean }
  proposal?: { productName?: string; category?: string; priceMinor?: number; quantity?: number; reason?: string }
  decision?: { code: string | null; reason?: string }
}

export interface ConversationMessage {
  id: string
  actor: ConversationActor
  text: string
  tone: ConversationTone
  timestamp: string | null
  evidence: ConversationEvidence | null
}

type Payload = Record<string, unknown> | null

function str(payload: Payload, key: string): string | undefined {
  const value = payload?.[key]
  return typeof value === 'string' ? value : undefined
}
function num(payload: Payload, key: string): number | undefined {
  const value = payload?.[key]
  return typeof value === 'number' ? value : undefined
}
function bool(payload: Payload, key: string): boolean | undefined {
  const value = payload?.[key]
  return typeof value === 'boolean' ? value : undefined
}
function strArray(payload: Payload, key: string): string[] | undefined {
  const value = payload?.[key]
  return Array.isArray(value) ? value.filter((v): v is string => typeof v === 'string') : undefined
}

function proposalEvidence(payload: Payload): ConversationEvidence['proposal'] {
  const productName = str(payload, 'proposed_product_name')
  if (!productName) return undefined
  return {
    productName,
    category: str(payload, 'proposed_category'),
    priceMinor: num(payload, 'proposed_price_minor'),
    quantity: num(payload, 'proposed_quantity'),
    reason: str(payload, 'proposed_reason'),
  }
}

function mandateEvidence(payload: Payload): ConversationEvidence['mandate'] {
  const maxAmountMinor = num(payload, 'mandate_max_amount_minor')
  if (maxAmountMinor === undefined) return undefined
  return {
    maxAmountMinor,
    allowedCategories: strArray(payload, 'mandate_allowed_categories'),
    allowAddons: bool(payload, 'mandate_allow_addons'),
  }
}

const BLOCK_REASONS = new Set(['HARD_POLICY_BLOCKED', 'CART_REVALIDATION_BLOCKED'])

export function eventsToConversation(events: AuditEventRecord[], cart?: CartResponse | null): ConversationMessage[] {
  const messages: ConversationMessage[] = []

  if (cart && cart.items.length > 0) {
    const itemList = cart.items.map((item) => `${item.quantity}x ${item.product_name}`).join(', ')
    messages.push({
      id: 'claude-cart-opener',
      actor: 'claude',
      text: `I found ${itemList} and added ${cart.items.length === 1 ? 'it' : 'them'} to the cart.`,
      tone: 'neutral',
      timestamp: null,
      evidence: null,
    })
  }

  for (const event of events) {
    const payload = event.payload

    if (event.event_type === 'PRODUCTS_SEARCHED') {
      const merchantName = str(payload, 'merchant_name')
      const resultCount = num(payload, 'result_count')
      const where = merchantName ? `at ${merchantName}` : 'across both merchants'
      const countText = resultCount !== undefined ? ` — found ${resultCount} product${resultCount === 1 ? '' : 's'}` : ''
      messages.push(base(event, 'claude', `Searching ${where}${countText}…`, 'neutral'))
    } else if (event.event_type === 'PRODUCT_VIEWED') {
      const productName = str(payload, 'product_name')
      const merchantName = str(payload, 'merchant_name')
      const priceMinor = num(payload, 'price_minor')
      const currency = str(payload, 'currency') ?? 'INR'
      const priceText = priceMinor !== undefined ? ` — ${formatCurrency(priceMinor, currency)}` : ''
      messages.push(
        base(event, 'claude', `Looked at ${productName ?? 'a product'}${merchantName ? ` (${merchantName})` : ''}${priceText}.`, 'neutral'),
      )
    } else if (event.event_type === 'CART_CREATED') {
      const merchantName = str(payload, 'merchant_name')
      messages.push(
        base(event, 'claude', merchantName ? `Started shopping at ${merchantName}…` : 'Started a new cart…', 'neutral'),
      )
    } else if (event.event_type === 'CART_ITEM_ADDED') {
      const productName = str(payload, 'product_name')
      const quantity = num(payload, 'quantity')
      messages.push(base(event, 'claude', `Added ${quantity ?? 1}x ${productName ?? 'an item'} to the cart.`, 'neutral'))
    } else if (event.event_type === 'AUTHORIZATION_REQUESTED') {
      const productType = str(payload, 'product_type')
      const maxAmountMinor = num(payload, 'max_amount_minor')
      const categories = strArray(payload, 'allowed_categories')
      const reason = str(payload, 'reason')
      const amountText = maxAmountMinor !== undefined ? formatCurrency(maxAmountMinor, 'INR') : 'an amount'
      const categoryText = categories && categories.length > 0 ? categories.join(', ') : 'these items'
      messages.push({
        ...base(
          event,
          'claude',
          `I'd like to buy ${productType ?? 'this'} — up to ${amountText}, in ${categoryText}.${reason ? ` ${reason}` : ''}`,
          'checking',
        ),
        evidence: maxAmountMinor !== undefined ? { mandate: { maxAmountMinor, allowedCategories: categories } } : null,
      })
    } else if (event.event_type === 'AUTHORIZATION_APPROVED') {
      messages.push(base(event, 'agentpay', '✓ Authorization approved — mandate signed.', 'approved'))
    } else if (event.event_type === 'AUTHORIZATION_REJECTED') {
      messages.push(base(event, 'agentpay', '❌ Authorization rejected.', 'blocked'))
    } else if (event.event_type === 'MANDATE_CREATED') {
      messages.push(base(event, 'agentpay', 'Mandate received and verified.', 'pass'))
    } else if (event.event_type === 'HARD_POLICY_PASSED') {
      messages.push(base(event, 'agentpay', '✓ Hard policy checks passed.', 'pass'))
    } else if (BLOCK_REASONS.has(event.event_type)) {
      messages.push({
        ...base(event, 'agentpay', `❌ BLOCKED — ${event.reason_code ?? 'policy violation'}`, 'blocked'),
        evidence: { decision: { code: event.reason_code } },
      })
    } else if (event.event_type === 'MERCHANT_AGENT_STARTED') {
      messages.push(base(event, 'merchant', 'Let me check if there is a good add-on for this cart…', 'neutral'))
    } else if (event.event_type === 'MERCHANT_AGENT_NO_PROPOSAL') {
      messages.push(base(event, 'merchant', "Nothing seemed like a good fit — I'll keep the cart as is.", 'neutral'))
    } else if (event.event_type === 'MERCHANT_PROPOSAL_CREATED') {
      const proposal = proposalEvidence(payload)
      const price = proposal?.priceMinor !== undefined ? formatCurrency(proposal.priceMinor, 'INR') : ''
      messages.push({
        ...base(
          event,
          'merchant',
          proposal ? `I found ${proposal.productName} for ${price}. I recommend adding it.` : 'I have a proposal for this cart.',
          'neutral',
        ),
        evidence: { proposal },
      })
    } else if (event.event_type === 'INTENT_CHECK_STARTED') {
      messages.push({
        ...base(event, 'agentpay', '⚠️ Checking this proposal against your mandate…', 'checking'),
        evidence: { mandate: mandateEvidence(payload), proposal: proposalEvidence(payload) },
      })
    } else if (event.event_type === 'INTENT_GATE_ALLOWED') {
      messages.push({
        ...base(event, 'agentpay', '✓ APPROVED — consistent with your authorization.', 'approved'),
        evidence: { proposal: proposalEvidence(payload) },
      })
    } else if (event.event_type === 'INTENT_GATE_BLOCKED' || event.event_type === 'INTENT_ESCALATED') {
      const label = event.event_type === 'INTENT_ESCALATED' ? '⚠️ ESCALATED' : '❌ BLOCKED'
      messages.push({
        ...base(event, 'agentpay', `${label} — ${event.reason_code ?? 'needs review'}`, 'blocked'),
        evidence: {
          mandate: mandateEvidence(payload),
          proposal: proposalEvidence(payload),
          decision: { code: event.reason_code, reason: str(payload, 'reason') },
        },
      })
      messages.push(base(event, 'merchant', "Understood. I'll keep the original cart.", 'neutral', `${event.event_id}-ack`))
    } else if (event.event_type === 'CART_REVALIDATION_PASSED') {
      messages.push(base(event, 'agentpay', '✓ Final cart verified.', 'approved'))
    } else if (event.event_type === 'RAZORPAY_ORDER_CREATED') {
      messages.push(base(event, 'agentpay', 'Razorpay order created — ready for payment.', 'pass'))
    } else if (event.event_type === 'PAYMENT_CAPTURED') {
      messages.push(base(event, 'agentpay', '✓ Payment captured.', 'approved'))
    } else if (event.event_type === 'PAYMENT_FAILED' || event.event_type === 'TRANSACTION_BLOCKED') {
      messages.push(
        base(event, 'agentpay', `❌ Payment did not succeed${event.reason_code ? ` — ${event.reason_code}` : ''}.`, 'blocked'),
      )
    } else if (event.event_type === 'TRANSACTION_COMPLETED') {
      messages.push(base(event, 'agentpay', '✓ Order complete.', 'approved'))
    } else if (event.event_type === 'AUTOMATIC_PAYMENT_STARTED') {
      messages.push(base(event, 'agentpay', '✓ Payment authorization verified — automatic payment initiated…', 'checking'))
    } else if (event.event_type === 'AUTOMATIC_PAYMENT_AUTHORIZED') {
      messages.push(base(event, 'agentpay', 'Automatic payment authorized by Razorpay.', 'pass'))
    } else if (event.event_type === 'AUTOMATIC_PAYMENT_CAPTURED') {
      messages.push(base(event, 'agentpay', '✓ Automatic payment captured.', 'approved'))
    } else if (event.event_type === 'AUTOMATIC_PAYMENT_REQUIRES_AUTHENTICATION') {
      const detail = str(payload, 'error') ?? event.reason_code
      messages.push(
        base(
          event,
          'agentpay',
          `⚠️ Payment requires additional authentication — complete it manually to finish.${detail ? ` (${detail})` : ''}`,
          'blocked',
        ),
      )
    } else if (event.event_type === 'AUTOMATIC_PAYMENT_FAILED') {
      const detail = str(payload, 'error') ?? event.reason_code
      messages.push(
        base(
          event,
          'agentpay',
          `❌ Automatic payment did not succeed${detail ? ` — ${detail}` : ''}. Falling back to manual payment.`,
          'blocked',
        ),
      )
    }
    // CART_FROZEN, PROPOSAL_REJECTED, MANDATE_CONSUMED, RAZORPAY_EVENT_UNHANDLED, PAYMENT_AUTHORIZATION_*:
    // intentionally not their own bubble here. CART_FROZEN/MANDATE_CONSUMED are internal bookkeeping
    // already implied by the surrounding messages; PROPOSAL_REJECTED always fires alongside
    // INTENT_GATE_BLOCKED/INTENT_ESCALATED, which already renders both the blocked bubble and the
    // merchant's acknowledgment above; PAYMENT_AUTHORIZATION_* events describe the separate Automatic
    // Payments *setup* flow (plan.md Phase 5), not a specific transaction's own conversation.
  }

  return messages
}

function base(
  event: AuditEventRecord,
  actor: ConversationActor,
  text: string,
  tone: ConversationTone,
  id: string = event.event_id,
): ConversationMessage {
  return { id, actor, text, tone, timestamp: event.created_at, evidence: null }
}

/** True once the conversation has reached a terminal outcome (paid, failed, or fully blocked) -- used to stop showing the "typing" indicator. */
export function isConversationSettled(events: AuditEventRecord[]): boolean {
  return events.some((e) =>
    [
      'TRANSACTION_COMPLETED',
      'PAYMENT_CAPTURED',
      'PAYMENT_FAILED',
      'TRANSACTION_BLOCKED',
      'HARD_POLICY_BLOCKED',
      'CART_REVALIDATION_BLOCKED',
      'AUTHORIZATION_REJECTED',
    ].includes(e.event_type),
  )
}
