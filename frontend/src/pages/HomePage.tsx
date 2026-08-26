import { Link } from 'react-router-dom'
import { ProductGrid } from '../components/ProductGrid'
import { useProducts } from '../hooks/useProducts'

/** UrbanNest storefront home page: the full product catalog as a grid. */
export function HomePage() {
  const { data: products, loading, error } = useProducts()

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-lg font-semibold text-slate-900">UrbanNest</h1>
          <p className="text-sm text-slate-500">Shop directly, or hand your mandate_id to Claude to shop on your behalf.</p>
        </div>
        <Link
          to="/authorize-agent"
          className="shrink-0 rounded-md bg-indigo-600 px-3.5 py-2 text-sm font-medium text-white transition hover:bg-indigo-700"
        >
          🔐 Authorize an AI agent
        </Link>
      </div>
      {loading && <p className="text-sm text-slate-500">Loading products…</p>}
      {error && <p className="text-sm text-red-600">{error.message}</p>}
      {products && <ProductGrid products={products} />}
    </div>
  )
}
