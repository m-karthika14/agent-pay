import { formatCurrency } from '../lib/formatCurrency'
import type { CartItemResponse } from '../types/cart'

interface CartItemRowProps {
  item: CartItemResponse
  currency: string
  disabled: boolean
  onUpdateQuantity: (quantity: number) => void
  onRemove: () => void
}

/** One line item within the cart page, with quantity +/- controls and a remove button. */
export function CartItemRow({ item, currency, disabled, onUpdateQuantity, onRemove }: CartItemRowProps) {
  return (
    <li className="flex items-center justify-between gap-4 py-3">
      <div className="min-w-0">
        <p className="truncate text-sm font-medium text-slate-800">{item.product_name}</p>
        <p className="text-xs text-slate-400">{formatCurrency(item.unit_price_minor, currency)} each</p>
      </div>
      <div className="flex items-center gap-3">
        <div className="flex items-center rounded-md border border-slate-200">
          <button
            type="button"
            disabled={disabled || item.quantity <= 1}
            onClick={() => onUpdateQuantity(item.quantity - 1)}
            className="px-2 py-1 text-sm text-slate-600 disabled:opacity-30"
          >
            −
          </button>
          <span className="w-8 text-center text-sm">{item.quantity}</span>
          <button
            type="button"
            disabled={disabled}
            onClick={() => onUpdateQuantity(item.quantity + 1)}
            className="px-2 py-1 text-sm text-slate-600 disabled:opacity-30"
          >
            +
          </button>
        </div>
        <span className="w-20 text-right text-sm font-medium text-slate-900">
          {formatCurrency(item.line_total_minor, currency)}
        </span>
        <button
          type="button"
          disabled={disabled}
          onClick={onRemove}
          className="text-xs text-red-500 hover:text-red-700 disabled:opacity-30"
        >
          Remove
        </button>
      </div>
    </li>
  )
}
