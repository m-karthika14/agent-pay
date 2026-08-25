import { formatDate } from '../lib/formatDate'
import type { AuditEventRecord } from '../types/audit'

interface ActivityTimelineProps {
  events: AuditEventRecord[]
}

type StepState = 'done' | 'blocked' | 'pending'

interface Step {
  label: string
  /** Audit event_types that satisfy this step, checked in order (first match wins). */
  matchTypes: string[]
  /** event_types among matchTypes that represent a blocked/failed outcome rather than success. */
  blockedTypes?: string[]
  /** Only rendered once a matching event exists -- e.g. a merchant proposal that never happened. */
  optional?: boolean
}

const STEPS: Step[] = [
  { label: 'Mandate authorized', matchTypes: ['MANDATE_CREATED'] },
  {
    label: 'Hard policy check',
    matchTypes: ['HARD_POLICY_PASSED', 'HARD_POLICY_BLOCKED', 'CART_REVALIDATION_PASSED', 'CART_REVALIDATION_BLOCKED'],
    blockedTypes: ['HARD_POLICY_BLOCKED', 'CART_REVALIDATION_BLOCKED'],
  },
  { label: 'Cart frozen', matchTypes: ['CART_FROZEN'] },
  { label: 'Merchant agent proposal', matchTypes: ['MERCHANT_PROPOSAL_CREATED'], optional: true },
  {
    label: 'AgentPay decision',
    matchTypes: ['INTENT_GATE_ALLOWED', 'INTENT_GATE_BLOCKED', 'INTENT_ESCALATED', 'PROPOSAL_REJECTED'],
    blockedTypes: ['INTENT_GATE_BLOCKED', 'INTENT_ESCALATED', 'PROPOSAL_REJECTED'],
    optional: true,
  },
  { label: 'Razorpay order created', matchTypes: ['RAZORPAY_ORDER_CREATED'] },
  {
    label: 'Payment settled',
    matchTypes: ['PAYMENT_CAPTURED', 'PAYMENT_FAILED', 'TRANSACTION_BLOCKED'],
    blockedTypes: ['PAYMENT_FAILED', 'TRANSACTION_BLOCKED'],
  },
  { label: 'Order completed', matchTypes: ['TRANSACTION_COMPLETED'] },
]

function findEvent(events: AuditEventRecord[], types: string[]): AuditEventRecord | undefined {
  return events.find((event) => types.includes(event.event_type))
}

const ICONS: Record<StepState, string> = { done: '✓', blocked: '✕', pending: '○' }
const CIRCLE_CLASSES: Record<StepState, string> = {
  done: 'border-emerald-500 bg-emerald-500 text-white',
  blocked: 'border-red-500 bg-red-500 text-white',
  pending: 'border-slate-300 bg-white text-slate-400',
}
const LABEL_CLASSES: Record<StepState, string> = {
  done: 'text-slate-900',
  blocked: 'text-red-700',
  pending: 'text-slate-400',
}

/**
 * Checkmark-style progress timeline translating raw audit events into the
 * buyer/judge-facing steps of one checkout (mandate -> hard checks -> cart
 * freeze -> merchant proposal -> AgentPay decision -> Razorpay -> order).
 * Purpose-built so judges can follow what's happening without reading raw
 * MCP console calls.
 */
export function ActivityTimeline({ events }: ActivityTimelineProps) {
  const visibleSteps = STEPS.filter((step) => !step.optional || findEvent(events, step.matchTypes))

  return (
    <ol className="space-y-4">
      {visibleSteps.map((step) => {
        const event = findEvent(events, step.matchTypes)
        const state: StepState = !event ? 'pending' : step.blockedTypes?.includes(event.event_type) ? 'blocked' : 'done'
        return (
          <li key={step.label} className="flex gap-3">
            <span
              className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full border text-xs font-bold ${CIRCLE_CLASSES[state]}`}
            >
              {ICONS[state]}
            </span>
            <div className="min-w-0 flex-1">
              <p className={`text-sm font-medium ${LABEL_CLASSES[state]}`}>{step.label}</p>
              {event && (
                <p className="text-xs text-slate-400">
                  {event.event_type}
                  {event.reason_code ? ` — ${event.reason_code}` : ''}
                  {event.created_at ? ` · ${formatDate(event.created_at)}` : ''}
                </p>
              )}
            </div>
          </li>
        )
      })}
    </ol>
  )
}
