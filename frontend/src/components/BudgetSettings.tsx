/**
 * The user's own "AI Shopping Budget" (plan.md Phase 4) -- an independent
 * spending ceiling set here, on the landing page, before Claude ever asks
 * for anything. This is the human's side of the defense-in-depth pair with
 * app.authorization.service: once set, it's an absolute ceiling Claude's
 * own request_authorization() calls cannot exceed, and a human's Edit in
 * the "Claude wants to buy" popup cannot push back above either.
 *
 * Deliberately lives only here, below "Logged in as ..." on the landing
 * page -- not inside any merchant's storefront -- since it's a property of
 * the buyer's AI shopping authority as a whole, not of any one store.
 */
import { useState } from 'react'
import { usePolling } from '../hooks/usePolling'
import * as budgetApi from '../services/budgetApi'
import { formatCurrency } from '../lib/formatCurrency'
import type { BudgetResponse } from '../types/budget'

const DURATIONS = [
  { label: '1 hour', hours: 1 },
  { label: '24 hours', hours: 24 },
  { label: '7 days', hours: 24 * 7 },
]

export function BudgetSettings({ userId }: { userId: string }) {
  const [refreshKey, setRefreshKey] = useState(0)
  const [editing, setEditing] = useState(false)
  const budget = usePolling(() => budgetApi.getBudget(userId), [userId, refreshKey], { intervalMs: 60_000 })

  if (!budget.data) return null

  if (!editing) {
    return (
      <div className="flex justify-center">
        {budget.data.is_active ? (
          <div className="flex items-center gap-2 rounded-full border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs text-slate-600">
            <span>
              💰 AI budget: <span className="font-medium text-slate-800">{formatCurrency(budget.data.max_amount_minor ?? 0, budget.data.currency)}</span>
              {budget.data.allow_addons ? ' · Add-ons allowed' : ' · Add-ons off'}
            </span>
            <button type="button" onClick={() => setEditing(true)} className="font-medium text-slate-500 underline hover:text-slate-700">
              Edit
            </button>
          </div>
        ) : (
          <button
            type="button"
            onClick={() => setEditing(true)}
            className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-100"
          >
            💰 Set AI shopping budget
          </button>
        )}
      </div>
    )
  }

  return (
    <BudgetForm
      userId={userId}
      current={budget.data}
      onDone={() => {
        setEditing(false)
        setRefreshKey((k) => k + 1)
      }}
      onCancel={() => setEditing(false)}
    />
  )
}

function BudgetForm({
  userId,
  current,
  onDone,
  onCancel,
}: {
  userId: string
  current: BudgetResponse
  onDone: () => void
  onCancel: () => void
}) {
  const [maxAmount, setMaxAmount] = useState(current.max_amount_minor !== null ? String(current.max_amount_minor / 100) : '5000')
  const [allowAddons, setAllowAddons] = useState(current.allow_addons ?? true)
  const [durationHours, setDurationHours] = useState(24)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSave() {
    setSubmitting(true)
    setError(null)
    try {
      await budgetApi.setBudget(userId, {
        max_amount_minor: Math.round(Number(maxAmount) * 100),
        allow_addons: allowAddons,
        expires_in_hours: durationHours,
      })
      onDone()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="mx-auto max-w-xs space-y-3 rounded-2xl border border-slate-200 bg-white p-4 text-left shadow-sm">
      <p className="text-center text-xs font-semibold tracking-wide text-slate-400 uppercase">🤖 AI Shopping Authority</p>

      <label className="block text-sm">
        <span className="text-slate-600">Maximum total spending (₹)</span>
        <input
          type="number"
          min="1"
          step="1"
          value={maxAmount}
          onChange={(e) => setMaxAmount(e.target.value)}
          className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
        />
        <span className="mt-1 block text-xs text-slate-400">Your AI agent can spend up to this amount on a purchase, including any add-ons.</span>
      </label>

      <label className="flex items-center gap-2 text-sm text-slate-600">
        <input type="checkbox" checked={allowAddons} onChange={(e) => setAllowAddons(e.target.checked)} />
        Allow relevant merchant add-ons
      </label>

      <fieldset>
        <legend className="text-sm text-slate-600">Expires in</legend>
        <div className="mt-1 flex gap-3">
          {DURATIONS.map((d) => (
            <label key={d.hours} className="flex items-center gap-1.5 text-sm text-slate-700">
              <input type="radio" name="budget-duration" checked={durationHours === d.hours} onChange={() => setDurationHours(d.hours)} />
              {d.label}
            </label>
          ))}
        </div>
      </fieldset>

      {error && <p className="text-sm text-red-600">{error}</p>}

      <div className="flex gap-2 pt-1">
        <button
          type="button"
          onClick={onCancel}
          className="flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
        >
          Cancel
        </button>
        <button
          type="button"
          disabled={submitting || Number(maxAmount) <= 0}
          onClick={() => void handleSave()}
          className="flex-1 rounded-md bg-slate-900 px-3 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-40"
        >
          {submitting ? 'Saving…' : 'Save budget'}
        </button>
      </div>
    </div>
  )
}
