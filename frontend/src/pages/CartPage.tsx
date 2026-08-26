import { Link, useNavigate } from 'react-router-dom'
import { CartItemRow } from '../components/CartItemRow'
import { useCart } from '../context/CartContext'
import { formatCurrency } from '../lib/formatCurrency'

/** Cart contents page: line items with quantity controls, subtotal, and a link into checkout. */
export function CartPage() {
  const { cart, loading, error, updateItem, removeItem } = useCart()
  const navigate = useNavigate()

  if (loading && !cart) return <p className="text-sm text-slate-500">Loading cart…</p>

  if (!cart || cart.items.length === 0) {
    return (
      <div className="space-y-3">
        <h1 className="text-lg font-semibold text-slate-900">Your cart</h1>
        <p className="text-sm text-slate-500">Your cart is empty.</p>
        <Link to="/" className="text-sm font-medium text-slate-900 underline">
          Browse products
        </Link>
      </div>
    )
  }

  return (
    <div className="max-w-xl space-y-4">
      <h1 className="text-lg font-semibold text-slate-900">Your cart</h1>
      {error && <p className="text-sm text-red-600">{error.message}</p>}
      <div className="rounded-lg border border-slate-200 bg-white px-4">
        <ul className="divide-y divide-slate-100">
          {cart.items.map((item) => (
            <CartItemRow
              key={item.item_id}
              item={item}
              currency={cart.currency}
              disabled={loading}
              onUpdateQuantity={(quantity) => void updateItem(item.item_id, quantity)}
              onRemove={() => void removeItem(item.item_id)}
            />
          ))}
        </ul>
      </div>
      <div className="flex items-center justify-between rounded-lg border border-slate-200 bg-white p-4">
        <span className="text-sm font-medium text-slate-600">Subtotal</span>
        <span className="text-lg font-semibold text-slate-900">{formatCurrency(cart.subtotal_minor, cart.currency)}</span>
      </div>
      <button
        type="button"
        onClick={() => navigate('/checkout')}
        className="w-full rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-indigo-700"
      >
        Authorize purchase
      </button>
    </div>
  )
}
