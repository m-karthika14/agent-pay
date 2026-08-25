import { Link, useParams } from 'react-router-dom'
import { DecisionTrace } from '../components/DecisionTrace'
import { MandateCard } from '../components/MandateCard'
import { PaymentStatus } from '../components/PaymentStatus'
import { StatusBadge } from '../components/StatusBadge'
import { useTransaction } from '../hooks/useTransaction'
import { formatCurrency } from '../lib/formatCurrency'

/**
 * One transaction's complete view (plan.md Section 19.2/24 "Transaction
 * view"): buyer, mandate, cart, Razorpay state, and the ordered decision
 * trace.
 */
export function TransactionPage() {
  const { transactionId } = useParams<{ transactionId: string }>()
  const { data, loading, error } = useTransaction(transactionId ?? '')

  if (loading) return <p className="text-sm text-slate-500">Loading…</p>
  if (error) return <p className="text-sm text-red-600">{error.message}</p>
  if (!data) return null

  return (
    <div className="space-y-6">
      <div>
        <Link to="/" className="text-sm text-slate-500 hover:text-slate-700">
          ← Back to console
        </Link>
        <h1 className="mt-1 text-lg font-semibold text-slate-900">Transaction {data.transaction.transaction_id}</h1>
        <p className="text-sm text-slate-500">
          Buyer: {data.buyer.name} ({data.buyer.email})
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <MandateCard mandate={data.mandate} currency={data.order.currency} />
        <PaymentStatus transaction={data.transaction} order={data.order} />
      </div>

      <div className="rounded-lg border border-slate-200 bg-white p-4">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-slate-800">Cart</h3>
          <StatusBadge status={data.cart.status} />
        </div>
        <ul className="mt-3 divide-y divide-slate-100 text-sm">
          {data.cart.items.map((item) => (
            <li key={item.item_id} className="flex justify-between py-2">
              <span className="text-slate-700">
                {item.quantity}x {item.product_name}
              </span>
              <span className="text-slate-600">{formatCurrency(item.line_total_minor, data.cart.currency)}</span>
            </li>
          ))}
        </ul>
        <div className="mt-2 flex justify-between border-t border-slate-100 pt-2 text-sm font-medium">
          <span>Subtotal</span>
          <span>{formatCurrency(data.cart.subtotal_minor, data.cart.currency)}</span>
        </div>
      </div>

      <div className="rounded-lg border border-slate-200 bg-white p-4">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-slate-800">Decision Trace</h3>
          <Link
            to={`/transactions/${data.transaction.transaction_id}/audit`}
            className="text-sm text-slate-500 hover:text-slate-700"
          >
            View audit chain →
          </Link>
        </div>
        <DecisionTrace events={data.events} />
      </div>
    </div>
  )
}
