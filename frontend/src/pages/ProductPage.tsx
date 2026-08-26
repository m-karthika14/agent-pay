import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { ProductImage } from '../components/ProductImage'
import { useBuyer } from '../context/BuyerContext'
import { useCart } from '../context/CartContext'
import { useProduct } from '../hooks/useProducts'
import { formatCurrency } from '../lib/formatCurrency'

/** Product detail page: price, category, stock, delivery, return policy, and add-to-cart. */
export function ProductPage() {
  const { productId } = useParams<{ productId: string }>()
  const { product, inventory } = useProduct(productId)
  const { addItem, loading: cartLoading } = useCart()
  const { userId, loading: buyerLoading, error: buyerError } = useBuyer()
  const navigate = useNavigate()
  const [adding, setAdding] = useState(false)
  const [addError, setAddError] = useState<Error | null>(null)

  if (product.loading) return <p className="text-sm text-slate-500">Loading…</p>
  if (product.error) return <p className="text-sm text-red-600">{product.error.message}</p>
  if (!product.data) return null

  const p = product.data
  const inStock = inventory.data ? inventory.data.available_quantity > 0 : true

  async function handleAddToCart() {
    if (!productId) return
    setAdding(true)
    setAddError(null)
    try {
      await addItem(productId, p.merchant_id, 1)
      navigate('/cart')
    } catch (err) {
      setAddError(err instanceof Error ? err : new Error(String(err)))
    } finally {
      setAdding(false)
    }
  }

  return (
    <div className="grid max-w-3xl gap-8 sm:grid-cols-2">
      <ProductImage category={p.category} className="aspect-square rounded-2xl" />

      <div className="space-y-4">
        <p className="text-xs font-semibold tracking-wide text-indigo-500 uppercase">{p.category}</p>
        <h1 className="text-xl font-semibold text-slate-900">{p.name}</h1>
        <p className="text-sm text-slate-600">{p.description}</p>
        <p className="text-2xl font-bold text-slate-900">{formatCurrency(p.price_minor, p.currency)}</p>

        <dl className="grid grid-cols-2 gap-3 rounded-lg border border-slate-200 bg-white p-4 text-sm">
          <div>
            <dt className="text-xs text-slate-400">Stock</dt>
            <dd className="text-slate-800">
              {inventory.data ? `${inventory.data.available_quantity} available` : '—'}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-slate-400">Delivery</dt>
            <dd className="text-slate-800">{p.delivery}</dd>
          </div>
          <div className="col-span-2">
            <dt className="text-xs text-slate-400">Returns</dt>
            <dd className="text-slate-800">{p.return_policy}</dd>
          </div>
        </dl>

        <button
          type="button"
          disabled={!inStock || adding || cartLoading || buyerLoading || !userId}
          onClick={handleAddToCart}
          className="w-full rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-indigo-700 disabled:opacity-40"
        >
          {!inStock ? 'Out of stock' : buyerLoading ? 'Preparing your session…' : adding ? 'Adding…' : 'Add to cart'}
        </button>
        {addError && <p className="text-sm text-red-600">{addError.message}</p>}
        {buyerError && <p className="text-sm text-red-600">Could not start your session: {buyerError.message}</p>}
      </div>
    </div>
  )
}
