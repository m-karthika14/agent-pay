import { formatCurrency } from '../lib/formatCurrency'
import { formatDate } from '../lib/formatDate'
import { StatusBadge } from './StatusBadge'
import type { OrderSummary, TransactionResponse } from '../types/transaction'

interface PaymentStatusProps {
  transaction: TransactionResponse
  order: OrderSummary
}

/** Shows the Razorpay payment/order state for a transaction (plan.md Section 24 "Razorpay state" panel). */
export function PaymentStatus({ transaction, order }: PaymentStatusProps) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-800">Razorpay Status</h3>
        <StatusBadge status={transaction.status} />
      </div>
      <dl className="mt-3 space-y-1.5 text-sm">
        <div className="flex justify-between">
          <dt className="text-slate-500">Amount</dt>
          <dd className="font-medium text-slate-800">{formatCurrency(order.amount_minor, order.currency)}</dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-slate-500">Razorpay order</dt>
          <dd className="font-mono text-xs text-slate-600">{order.razorpay_order_id ?? '—'}</dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-slate-500">Payment</dt>
          <dd className="font-mono text-xs text-slate-600">{transaction.razorpay_payment_id ?? '—'}</dd>
        </div>
        {transaction.failure_message && (
          <div className="flex justify-between gap-4">
            <dt className="flex-none text-slate-500">Failure</dt>
            <dd className="text-right text-red-600">{transaction.failure_message}</dd>
          </div>
        )}
        <div className="flex justify-between">
          <dt className="text-slate-500">Updated</dt>
          <dd className="text-slate-600">{formatDate(transaction.updated_at)}</dd>
        </div>
      </dl>
    </div>
  )
}
