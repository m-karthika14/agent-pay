import { formatCurrency } from '../lib/formatCurrency'
import { StatusBadge } from './StatusBadge'
import type { MandateSummary } from '../types/transaction'

interface MandateCardProps {
  mandate: MandateSummary
  /** MandateSummary itself carries no currency field -- the owning order's is used (they always match a real checkout). */
  currency: string
}

/** Shows the signed mandate that authorized a transaction (plan.md Section 24 "signed mandate" panel). */
export function MandateCard({ mandate, currency }: MandateCardProps) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-800">Signed Mandate</h3>
        <StatusBadge status={mandate.status} />
      </div>
      <dl className="mt-3 space-y-1.5 text-sm">
        <div className="flex justify-between">
          <dt className="text-slate-500">Mandate ID</dt>
          <dd className="font-mono text-slate-700">{mandate.mandate_id}</dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-slate-500">Product type</dt>
          <dd className="text-slate-700">{mandate.product_type}</dd>
        </div>
        {mandate.notes && (
          <div className="flex justify-between gap-4">
            <dt className="flex-none text-slate-500">Notes</dt>
            <dd className="text-right text-slate-700">{mandate.notes}</dd>
          </div>
        )}
        <div className="flex justify-between">
          <dt className="text-slate-500">Spending cap</dt>
          <dd className="text-slate-700">{formatCurrency(mandate.max_amount_minor, currency)}</dd>
        </div>
        <div className="flex justify-between gap-4">
          <dt className="flex-none text-slate-500">Allowed categories</dt>
          <dd className="text-right text-slate-700">{mandate.allowed_categories.join(', ')}</dd>
        </div>
      </dl>
    </div>
  )
}
