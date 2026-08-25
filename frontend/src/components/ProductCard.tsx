import { Link } from 'react-router-dom'
import { formatCurrency } from '../lib/formatCurrency'
import type { ProductResponse } from '../types/product'

interface ProductCardProps {
  product: ProductResponse
}

/** A single catalog product tile, linking through to its product detail page. */
export function ProductCard({ product }: ProductCardProps) {
  return (
    <Link
      to={`/products/${product.product_id}`}
      className="flex flex-col rounded-lg border border-slate-200 bg-white p-4 transition hover:border-slate-300 hover:shadow-sm"
    >
      <p className="text-xs font-medium tracking-wide text-slate-400 uppercase">{product.category}</p>
      <h3 className="mt-1 text-sm font-semibold text-slate-900">{product.name}</h3>
      <p className="mt-1 line-clamp-2 text-xs text-slate-500">{product.description}</p>
      <p className="mt-3 text-base font-semibold text-slate-900">{formatCurrency(product.price_minor, product.currency)}</p>
    </Link>
  )
}
