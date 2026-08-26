import { useState } from 'react'
import type { FormEvent } from 'react'
import { useBuyer } from '../context/BuyerContext'
import { useProducts } from '../hooks/useProducts'
import { formatCurrency } from '../lib/formatCurrency'
import { createMandate } from '../services/mandateApi'
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
 */
export function AuthorizeAgentPage() {
  const { email, name } = useBuyer()
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
  const [result, setResult] = useState<MandateResponse | null>(null)
  const [copied, setCopied] = useState(false)

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
      setResult(mandate)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setSubmitting(false)
    }
  }

  async function handleCopy() {
    if (!result) return
    await navigator.clipboard.writeText(result.mandate_id)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  if (result) {
    return (
      <div className="mx-auto max-w-md space-y-4">
        <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-6 text-center">
          <p className="text-2xl">✓</p>
          <h1 className="mt-1 text-lg font-semibold text-emerald-900">Agent authorized</h1>
          <p className="mt-1 text-sm text-emerald-800">
            Claude can now shop UrbanNest for you, within this authorization.
          </p>
        </div>

        <dl className="space-y-2 rounded-lg border border-slate-200 bg-white p-4 text-sm">
          <div className="flex justify-between">
            <dt className="text-slate-500">Maximum</dt>
            <dd className="font-medium text-slate-900">{formatCurrency(result.max_amount_minor, result.currency)}</dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-slate-500">Allowed categories</dt>
            <dd className="font-medium text-slate-900">{result.allowed_categories.join(', ') || '—'}</dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-slate-500">Add-ons</dt>
            <dd className="font-medium text-slate-900">{result.allow_addons ? 'Allowed' : 'Not allowed'}</dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-slate-500">Expires</dt>
            <dd className="font-medium text-slate-900">{new Date(result.expires_at).toLocaleString()}</dd>
          </div>
        </dl>

        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <p className="text-xs font-medium tracking-wide text-slate-500 uppercase">mandate_id</p>
          <p className="mt-1 font-mono text-sm break-all text-slate-900">{result.mandate_id}</p>
          <button
            type="button"
            onClick={() => void handleCopy()}
            className="mt-3 w-full rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-indigo-700"
          >
            {copied ? 'Copied!' : 'Copy mandate ID'}
          </button>
        </div>

        <button
          type="button"
          onClick={() => setResult(null)}
          className="w-full text-center text-sm font-medium text-slate-500 underline hover:text-slate-700"
        >
          Authorize another
        </button>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-md space-y-6">
      <div>
        <h1 className="text-lg font-semibold text-slate-900">Authorize an AI agent</h1>
        <p className="text-sm text-slate-500">
          Set the rules Claude has to shop within, then hand it the resulting mandate_id in conversation.
        </p>
      </div>

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
    </div>
  )
}
