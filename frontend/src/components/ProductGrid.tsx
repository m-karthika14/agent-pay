import { ProductCard } from './ProductCard'
import type { ProductResponse } from '../types/product'

interface ProductGridProps {
  products: ProductResponse[]
}

/** Responsive grid of product tiles for the storefront's HomePage. */
export function ProductGrid({ products }: ProductGridProps) {
  if (products.length === 0) {
    return <p className="text-sm text-slate-500">No products available.</p>
  }
  return (
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
      {products.map((product) => (
        <ProductCard key={product.product_id} product={product} />
      ))}
    </div>
  )
}
