import { useState } from 'react'
import type { FormEvent } from 'react'
import { useBuyer } from '../context/BuyerContext'
import { useAsync } from '../hooks/useAsync'
import { useProducts } from '../hooks/useProducts'
import { formatCurrency } from '../lib/formatCurrency'
import { formatDate } from '../lib/formatDate'
import { createMandate, listMandatesForUser } from '../services/mandateApi'
import type { MandateResponse } from '../types/mandate'

const DEFAULT_HOURS = 24

/**
 * Authorize an AI agent (e.g. Claude, via MCP) to shop UrbanNest on the
 * buyer's behalf -- independent of /checkout's mandate.
 *
 * /checkout's "Authorize purchase" creates a mandate and immediately
 * freezes the browser's own current cart under it in the same step -- it's
 * for a human buying what's already in their cart, not for handing
 * authority to an agent that hasn't shopped yet. This page calls the exact
 * same POST /api/mandates the backend has always supported for that
 * cart-less case (app.mandates.service.create_mandate_from_request never
 * required a cart -- the gap was only that no UI existed for it): a
 * mandate created here is ACTIVE and cart-less until whatever agent holds
 * its mandate_id eventually calls request_checkout() against a cart of its
 * own choosing.
 *
 * Every mandate this buyer has ever authorized stays listed below the form
 * (GET /api/mandates/by-user/{user_id}) -- a mandate_id used to be visible
 * only once, right after creation, and gone the moment you navigated away
 * without copying it.
 */
export function AuthorizeAgentPage() {
  const { userId, email, name } = useBuyer()
  const { data: products } = useProducts()

  const [maxAmount, setMaxAmount] = useState('')
  const [selectedCategories, setSelectedCategories] = useState<Set<string>>(new Set())
  const [allowAddons, setAllowAddons] = useState(false)
  const [productType, setProductType] = useState('')
  const [notes, setNotes] = useState('')
  const [expiresInHours, setExpiresInHours] = useState(DEFAULT_HOURS)
  const [singleUse, setSingleUse] = useState(true)

  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [justCreated, setJustCreated] = useState<MandateResponse | null>(null)
  const [refreshKey, setRefreshKey] = useState(0)

  const fetchMandates = (): Promise<MandateResponse[]> =>
    userId ? listMandatesForUser(userId) : Promise.reject(new Error('Not logged in.'))
  const mandates = useAsync<MandateResponse[]>(fetchMandates, [userId, refreshKey])

  const categories = [...new Set((products ?? []).map((p) => p.category))].sort()
  const merchantId = products?.[0]?.merchant_id

  function toggleCategory(category: string) {
    setSelectedCategories((prev) => {
      const next = new Set(prev)
      if (next.has(category)) next.delete(category)
      else next.add(category)
      return next
    })
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (!email || !merchantId) return
    setSubmitting(true)
    setError(null)
    try {
      const mandate = await createMandate({
        user_email: email,
        user_name: name ?? undefined,
        merchant_id: merchantId,
        currency: 'INR',
        max_amount_minor: Math.round(Number(maxAmount) * 100),
        allowed_categories: [...selectedCategories],
        allow_addons: allowAddons,
        delivery_requirement: 'under_3_days',
        single_use: singleUse,
        expires_in_hours: expiresInHours,
        product_type: productType,
        notes: notes || null,
      })
      setJustCreated(mandate)
      setRefreshKey((k) => k + 1)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="mx-auto max-w-md space-y-8">
      <div>
        <h1 className="text-lg font-semibold text-slate-900">Authorize an AI agent</h1>
        <p className="text-sm text-slate-500">
          Set the rules Claude has to shop within, then hand it the resulting mandate_id in conversation.
        </p>
      </div>

      {justCreated ? (
        <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-6 text-center">
          <p className="text-2xl">✓</p>
          <h2 className="mt-1 text-base font-semibold text-emerald-900">Agent authorized</h2>
          <p className="mt-1 text-sm text-emerald-800">Claude can now shop UrbanNest for you, within this authorization.</p>
          <p className="mt-3 rounded-md bg-white px-3 py-2 font-mono text-sm break-all text-slate-900">{justCreated.mandate_id}</p>
          <button
            type="button"
            onClick={() => setJustCreated(null)}
            className="mt-3 text-sm font-medium text-emerald-700 underline hover:text-emerald-900"
          >
            Authorize another
          </button>
        </div>
      ) : (
        <form onSubmit={(e) => void handleSubmit(e)} className="space-y-4 rounded-lg border border-slate-200 bg-white p-4">
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div>
              <p className="text-xs text-slate-400">Agent</p>
              <p className="font-medium text-slate-800">Claude</p>
            </div>
            <div>
              <p className="text-xs text-slate-400">Merchant</p>
              <p className="font-medium text-slate-800">UrbanNest</p>
            </div>
          </div>

          <label className="block text-sm">
            <span className="text-slate-600">Maximum spending (₹)</span>
            <input
              type="number"
              required
              min="1"
              step="1"
              value={maxAmount}
              onChange={(e) => setMaxAmount(e.target.value)}
              className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none"
              placeholder="3000"
            />
          </label>

          <label className="block text-sm">
            <span className="text-slate-600">What should the agent shop for?</span>
            <input
              type="text"
              required
              value={productType}
              onChange={(e) => setProductType(e.target.value)}
              className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none"
              placeholder="e.g. wireless earbuds"
            />
          </label>

          <fieldset>
            <legend className="text-sm text-slate-600">Allowed categories</legend>
            <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1.5">
              {categories.map((category) => (
                <label key={category} className="flex items-center gap-1.5 text-sm text-slate-700 capitalize">
                  <input
                    type="checkbox"
                    checked={selectedCategories.has(category)}
                    onChange={() => toggleCategory(category)}
                    className="accent-indigo-600"
                  />
                  {category}
                </label>
              ))}
            </div>
          </fieldset>

          <label className="flex items-center gap-2 text-sm text-slate-600">
            <input type="checkbox" checked={allowAddons} onChange={(e) => setAllowAddons(e.target.checked)} className="accent-indigo-600" />
            Allow the merchant to propose add-ons
          </label>

          <label className="block text-sm">
            <span className="text-slate-600">Notes for the agent (optional)</span>
            <input
              type="text"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none"
              placeholder="e.g. no unnecessary accessories"
            />
          </label>

          <div className="grid grid-cols-2 gap-3">
            <label className="block text-sm">
              <span className="text-slate-600">Valid for (hours)</span>
              <input
                type="number"
                required
                min="1"
                value={expiresInHours}
                onChange={(e) => setExpiresInHours(Number(e.target.value))}
                className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none"
              />
            </label>
            <label className="mt-1 flex items-center gap-2 self-end pb-2 text-sm text-slate-600">
              <input type="checkbox" checked={singleUse} onChange={(e) => setSingleUse(e.target.checked)} className="accent-indigo-600" />
              Single use
            </label>
          </div>

          <button
            type="submit"
            disabled={submitting || !email || !merchantId || selectedCategories.size === 0}
            className="w-full rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-indigo-700 disabled:opacity-40"
          >
            {submitting ? 'Authorizing…' : 'Authorize'}
          </button>
          {error && <p className="text-sm text-red-600">{error}</p>}
        </form>
      )}

      <div>
        <h2 className="mb-2 text-sm font-semibold text-slate-700">Your mandates</h2>
        {mandates.loading && <p className="text-sm text-slate-500">Loading…</p>}
        {mandates.data && mandates.data.length === 0 && <p className="text-sm text-slate-500">You haven't authorized any agents yet.</p>}
        {mandates.data && mandates.data.length > 0 && (
          <ul className="divide-y divide-slate-100 overflow-hidden rounded-lg border border-slate-200 bg-white">
            {mandates.data.map((mandate) => (
              <MandateRow key={mandate.mandate_id} mandate={mandate} />
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}

function MandateRow({ mandate }: { mandate: MandateResponse }) {
  const [copied, setCopied] = useState(false)

  async function handleCopy() {
    await navigator.clipboard.writeText(mandate.mandate_id)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <li className="flex items-center justify-between gap-3 px-4 py-3">
      <div className="min-w-0">
        <p className="truncate font-mono text-sm text-slate-900">{mandate.mandate_id}</p>
        <p className="text-xs text-slate-400">
          {formatCurrency(mandate.max_amount_minor, mandate.currency)} &middot; {mandate.status} &middot; expires{' '}
          {formatDate(mandate.expires_at)}
        </p>
      </div>
      <button
        type="button"
        onClick={() => void handleCopy()}
        className="shrink-0 rounded-md bg-slate-100 px-2.5 py-1.5 text-xs font-medium text-slate-700 transition hover:bg-slate-200"
      >
        {copied ? 'Copied!' : 'Copy'}
      </button>
    </li>
  )
}
