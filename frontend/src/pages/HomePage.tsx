import { Link, useParams } from 'react-router-dom'
import { ProductGrid } from '../components/ProductGrid'
import { useMerchants } from '../hooks/useMerchants'
import { useProducts } from '../hooks/useProducts'
import { getMerchantTheme } from '../lib/merchantTheme'

/** A single merchant's storefront home page: its product catalog as a grid. */
export function HomePage() {
  const { merchantSlug } = useParams<{ merchantSlug: string }>()
  const { data: products, loading, error } = useProducts(merchantSlug)
  const { data: merchants } = useMerchants()
  const theme = getMerchantTheme(merchantSlug)
  const merchantName = merchants?.find((m) => m.slug === merchantSlug)?.name ?? merchantSlug

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-lg font-semibold text-slate-900">{merchantName}</h1>
          <p className="text-sm text-slate-500">Shop directly, or hand your mandate_id to Claude to shop on your behalf.</p>
        </div>
        <Link
          to="/authorize-agent"
          className={`shrink-0 rounded-md px-3.5 py-2 text-sm font-medium text-white transition ${theme.primaryButton}`}
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
