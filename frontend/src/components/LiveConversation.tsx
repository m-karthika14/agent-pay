import { useState } from 'react'
import { eventsToConversation, isConversationSettled } from '../lib/eventsToConversation'
import { formatCurrency } from '../lib/formatCurrency'
import { formatTime } from '../lib/formatDate'
import type { ConversationMessage, ConversationTone } from '../lib/eventsToConversation'
import type { AuditEventRecord } from '../types/audit'
import type { CartResponse } from '../types/cart'

interface LiveConversationProps {
  events: AuditEventRecord[]
  /** The cart's real contents, if already fetched -- renders Claude's one opening line. Optional; the conversation works without it. */
  cart?: CartResponse | null
}

const ACTOR_META: Record<ConversationMessage['actor'], { label: string; icon: string; align: 'left' | 'right' }> = {
  claude: { label: 'Claude', icon: '🤖', align: 'left' },
  agentpay: { label: 'AgentPay', icon: '🛡️', align: 'left' },
  merchant: { label: 'Merchant Agent', icon: '💰', align: 'right' },
}

const BUBBLE_CLASS: Record<ConversationTone, string> = {
  neutral: 'bg-slate-100 text-slate-800',
  pass: 'bg-slate-100 text-slate-800',
  checking: 'bg-amber-50 text-amber-800 border border-amber-200',
  blocked: 'bg-red-50 text-red-800 border border-red-200',
  approved: 'bg-emerald-50 text-emerald-800 border border-emerald-200',
}

/**
 * Renders AgentPay's real audit trail as a live, WhatsApp-style
 * conversation (plan.md's storefront "AI Activity" panel) -- every message
 * is a translation of an actual backend event (see lib/eventsToConversation),
 * not an animation invented on the frontend.
 */
export function LiveConversation({ events, cart }: LiveConversationProps) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const messages = eventsToConversation(events, cart)
  const settled = isConversationSettled(events)
  const lastMessage = messages[messages.length - 1]
  const typingActor = lastMessage?.actor === 'merchant' ? 'agentpay' : 'merchant'

  function toggle(id: string) {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  return (
    <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white">
      <div className="flex items-center gap-2 border-b border-slate-100 px-4 py-3">
        <span className="relative flex h-2.5 w-2.5">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-red-400 opacity-75" />
          <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-red-500" />
        </span>
        <h2 className="text-sm font-semibold tracking-wide text-slate-700 uppercase">Live Agent Activity</h2>
      </div>

      <div className="space-y-4 px-4 py-4">
        {messages.length === 0 && <p className="text-sm text-slate-400">Waiting for the first event…</p>}

        {messages.map((message) => (
          <MessageBubble key={message.id} message={message} expanded={expanded.has(message.id)} onToggle={() => toggle(message.id)} />
        ))}

        {!settled && messages.length > 0 && <TypingBubble actor={typingActor} />}
      </div>

      <div className="border-t border-slate-100 px-4 py-2.5 text-xs font-medium text-slate-500">
        {settled ? '✓ Settled' : (
          <span className="inline-flex items-center gap-1.5">
            <span className="h-1.5 w-1.5 rounded-full bg-red-500" /> LIVE • Transaction in progress
          </span>
        )}
      </div>
    </div>
  )
}

function MessageBubble({
  message,
  expanded,
  onToggle,
}: {
  message: ConversationMessage
  expanded: boolean
  onToggle: () => void
}) {
  const meta = ACTOR_META[message.actor]
  const alignRight = meta.align === 'right'
  const hasEvidence = message.evidence !== null

  return (
    <div className={`animate-message-in flex flex-col ${alignRight ? 'items-end' : 'items-start'}`}>
      <span className="mb-1 text-xs font-medium text-slate-500">
        {meta.icon} {meta.label}
      </span>
      <button
        type="button"
        onClick={hasEvidence ? onToggle : undefined}
        className={`max-w-[85%] rounded-2xl px-3.5 py-2 text-left text-sm ${BUBBLE_CLASS[message.tone]} ${
          hasEvidence ? 'cursor-pointer hover:brightness-95' : 'cursor-default'
        }`}
      >
        {message.text}
        {hasEvidence && <span className="ml-1.5 text-xs opacity-60">{expanded ? '▲ hide details' : '▼ why?'}</span>}
      </button>
      {message.timestamp && (
        <span className="mt-1 text-[11px] text-slate-400">{formatTime(message.timestamp)} ✓</span>
      )}
      {hasEvidence && expanded && <EvidencePanel evidence={message.evidence!} alignRight={alignRight} />}
    </div>
  )
}

function EvidencePanel({ evidence, alignRight }: { evidence: NonNullable<ConversationMessage['evidence']>; alignRight: boolean }) {
  return (
    <div
      className={`mt-2 max-w-[85%] space-y-2 rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs text-slate-700 ${
        alignRight ? 'text-right' : 'text-left'
      }`}
    >
      {evidence.mandate && (
        <div>
          <p className="font-semibold text-slate-500 uppercase">User mandate</p>
          {evidence.mandate.maxAmountMinor !== undefined && <p>Maximum: {formatCurrency(evidence.mandate.maxAmountMinor, 'INR')}</p>}
          {evidence.mandate.allowedCategories && <p>Allowed categories: {evidence.mandate.allowedCategories.join(', ')}</p>}
          <p>Add-ons authorized: {evidence.mandate.allowAddons ? 'Yes' : 'No'}</p>
        </div>
      )}
      {evidence.proposal && (
        <div>
          <p className="font-semibold text-slate-500 uppercase">Proposal</p>
          <p>
            {evidence.proposal.productName}
            {evidence.proposal.priceMinor !== undefined ? ` — ${formatCurrency(evidence.proposal.priceMinor, 'INR')}` : ''}
          </p>
          {evidence.proposal.category && <p>Category: {evidence.proposal.category}</p>}
          {evidence.proposal.reason && <p className="italic">"{evidence.proposal.reason}"</p>}
        </div>
      )}
      {evidence.decision && (
        <div>
          <p className="font-semibold text-slate-500 uppercase">Decision</p>
          <p>{evidence.decision.code ?? '—'}</p>
          {evidence.decision.reason && <p className="italic">"{evidence.decision.reason}"</p>}
        </div>
      )}
    </div>
  )
}

function TypingBubble({ actor }: { actor: ConversationMessage['actor'] }) {
  const meta = ACTOR_META[actor]
  return (
    <div className={`flex flex-col ${meta.align === 'right' ? 'items-end' : 'items-start'}`}>
      <span className="mb-1 text-xs font-medium text-slate-400">
        {meta.icon} {meta.label}
      </span>
      <span className="flex items-center gap-1 rounded-2xl bg-slate-100 px-3.5 py-2.5">
        <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400 [animation-delay:-0.3s]" />
        <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400 [animation-delay:-0.15s]" />
        <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400" />
      </span>
    </div>
  )
}
