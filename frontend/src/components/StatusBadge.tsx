interface StatusBadgeProps {
  status: string
}

/**
 * Color rules for a status/decision string, checked in order (first
 * substring match wins) -- keeps color-coding consistent everywhere a
 * status or decision appears (hard-policy PASS/BLOCK, intent gate
 * ALLOW/BLOCK/ESCALATE, payment PENDING/CAPTURED/FAILED, cart OPEN/FROZEN).
 */
const COLOR_RULES: [substring: string, className: string][] = [
  ['BLOCK', 'bg-red-100 text-red-800'],
  ['FAIL', 'bg-red-100 text-red-800'],
  ['REJECT', 'bg-red-100 text-red-800'],
  ['ESCALAT', 'bg-amber-100 text-amber-800'],
  ['PASS', 'bg-emerald-100 text-emerald-800'],
  ['ALLOW', 'bg-emerald-100 text-emerald-800'],
  ['CAPTURED', 'bg-emerald-100 text-emerald-800'],
  ['PAID', 'bg-emerald-100 text-emerald-800'],
  ['COMPLETED', 'bg-emerald-100 text-emerald-800'],
  ['FROZEN', 'bg-blue-100 text-blue-800'],
]
const DEFAULT_COLOR_CLASS = 'bg-slate-100 text-slate-700'

/**
 * Small colored pill for a status/decision string (e.g. "PASS", "BLOCK",
 * "CAPTURED"). Used throughout the console/transaction/audit pages so a
 * given outcome always reads the same color.
 */
export function StatusBadge({ status }: StatusBadgeProps) {
  const normalized = status.toUpperCase()
  const colorClass = COLOR_RULES.find(([substring]) => normalized.includes(substring))?.[1] ?? DEFAULT_COLOR_CLASS
  return (
    <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium whitespace-nowrap ${colorClass}`}>
      {status}
    </span>
  )
}
