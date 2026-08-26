import { Link } from 'react-router-dom'
import { StatusBadge } from '../components/StatusBadge'
import { useBuyer } from '../context/BuyerContext'
import { useAsync } from '../hooks/useAsync'
import { formatCurrency } from '../lib/formatCurrency'
import { formatDate } from '../lib/formatDate'
import { getOrderHistory } from '../services/orderApi'
import type { OrderHistoryEntry } from '../types/transaction'

/** Buying history page: every order this demo buyer has ever placed, newest first. Wrapped in RequireBuyer, so a logged-in buyer is guaranteed. */
export function HistoryPage() {
  const { userId } = useBuyer()

  const fetchHistory = (): Promise<OrderHistoryEntry[]> =>
    userId ? getOrderHistory(userId) : Promise.reject(new Error('Not logged in.'))
  const { data: orders, loading, error } = useAsync<OrderHistoryEntry[]>(fetchHistory, [userId])

  return (
    <div className="max-w-2xl space-y-4">
      <h1 className="text-lg font-semibold text-slate-900">Buying History</h1>

      {loading && <p className="text-sm text-slate-500">Loading…</p>}
      {error && <p className="text-sm text-red-600">{error.message}</p>}

      {orders && orders.length === 0 && (
        <div className="space-y-3">
          <p className="text-sm text-slate-500">You haven't placed any orders yet.</p>
          <Link to="/" className="inline-block text-sm font-medium text-slate-900 underline">
            Browse products
          </Link>
        </div>
      )}

      {orders && orders.length > 0 && (
        <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
          <ul className="divide-y divide-slate-100">
            {orders.map((order) => (
              <li key={order.order_id}>
                <Link
                  to={`/order/${order.order_id}?mandate=${order.mandate_id}`}
                  className="flex items-center justify-between gap-4 px-4 py-3 text-sm hover:bg-slate-50"
                >
                  <div className="min-w-0">
                    <p className="truncate text-slate-800">{order.item_summary}</p>
                    <p className="text-xs text-slate-400">{formatDate(order.created_at)}</p>
                  </div>
                  <div className="flex shrink-0 items-center gap-3">
                    <span className="font-medium text-slate-900">
                      {formatCurrency(order.amount_minor, order.currency)}
                    </span>
                    <StatusBadge status={order.status} />
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
