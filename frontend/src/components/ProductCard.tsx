import { Link } from 'react-router-dom'
import { ProductImage } from './ProductImage'
import { formatCurrency } from '../lib/formatCurrency'
import { getMerchantTheme } from '../lib/merchantTheme'
import type { ProductResponse } from '../types/product'

interface ProductCardProps {
  product: ProductResponse
}

/** A single catalog product tile, linking through to its product detail page within its own merchant's store. */
export function ProductCard({ product }: ProductCardProps) {
  const theme = getMerchantTheme(product.merchant_slug)
  return (
    <Link
      to={`/store/${product.merchant_slug}/products/${product.product_id}`}
      className={`group flex flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white transition hover:-translate-y-0.5 hover:shadow-lg ${theme.cardHover}`}
    >
      <ProductImage category={product.category} name={product.name} className="aspect-square transition group-hover:scale-105" />
      <div className="flex flex-1 flex-col gap-1 p-4">
        <p className={`text-[11px] font-semibold tracking-wide uppercase ${theme.accentText}`}>{product.category}</p>
        <h3 className="text-sm font-semibold text-slate-900">{product.name}</h3>
        <p className="line-clamp-2 text-xs text-slate-500">{product.description}</p>
        <p className="mt-2 text-base font-bold text-slate-900">{formatCurrency(product.price_minor, product.currency)}</p>
      </div>
    </Link>
  )
}
