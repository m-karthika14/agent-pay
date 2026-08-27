import type { ReactNode } from 'react'

interface ProductImageProps {
  category: string
  /** The product's full name, e.g. "boAt Airdopes 141" -- its first word is treated as the brand for the wordmark + accent color below. */
  name?: string
  className?: string
}

interface CategoryArt {
  icon: ReactNode
}

/** One simple line-art SVG icon per catalog category, drawn inline so the storefront never depends on external image hosting. */
const ICONS: Record<string, ReactNode> = {
  audio: (
    <path
      d="M4 13a8 8 0 0 1 16 0v5a2 2 0 0 1-2 2h-1v-6h3M4 13v6h3v-6H4M4 13a8 8 0 0 1 8-8"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  ),
  wearables: (
    <g strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <rect x="7" y="7" width="10" height="10" rx="2.5" />
      <path d="M9 7V4h6v3M9 17v3h6v-3M12 10v4" />
    </g>
  ),
  power: (
    <g strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <rect x="6" y="7" width="10" height="14" rx="2" />
      <path d="M9 4h4v3H9zM13 11l-3 4h3l-3 4" />
    </g>
  ),
  accessories: (
    <g strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 3 4 8v8l8 5 8-5V8z" />
      <path d="M4 8l8 5 8-5M12 13v8" />
    </g>
  ),
}

const CATEGORY_ART: Record<string, CategoryArt> = {
  audio: { icon: ICONS.audio },
  wearables: { icon: ICONS.wearables },
  power: { icon: ICONS.power },
  accessories: { icon: ICONS.accessories },
}
const DEFAULT_ART: CategoryArt = { icon: ICONS.accessories }

/**
 * A small, fixed palette of distinct accent colors, picked by a stable hash
 * of the product's brand -- every "boAt" product lands on the same color
 * across the whole catalog, every "Noise" product on a different one, and
 * so on, without needing a hand-maintained brand->color table.
 */
const BRAND_PALETTE = [
  { bg: 'from-orange-100 to-orange-200', text: 'text-orange-600' },
  { bg: 'from-teal-100 to-teal-200', text: 'text-teal-600' },
  { bg: 'from-blue-100 to-blue-200', text: 'text-blue-600' },
  { bg: 'from-rose-100 to-rose-200', text: 'text-rose-600' },
  { bg: 'from-purple-100 to-purple-200', text: 'text-purple-600' },
  { bg: 'from-emerald-100 to-emerald-200', text: 'text-emerald-700' },
  { bg: 'from-amber-100 to-amber-200', text: 'text-amber-700' },
  { bg: 'from-cyan-100 to-cyan-200', text: 'text-cyan-700' },
  { bg: 'from-indigo-100 to-indigo-200', text: 'text-indigo-600' },
  { bg: 'from-pink-100 to-pink-200', text: 'text-pink-600' },
]
const DEFAULT_PALETTE = { bg: 'from-slate-100 to-slate-200', text: 'text-slate-500' }

function brandOf(name: string): string {
  return name.trim().split(' ')[0] ?? ''
}

function paletteFor(brand: string): (typeof BRAND_PALETTE)[number] {
  if (!brand) return DEFAULT_PALETTE
  let hash = 0
  for (let i = 0; i < brand.length; i++) hash = (hash * 31 + brand.charCodeAt(i)) >>> 0
  return BRAND_PALETTE[hash % BRAND_PALETTE.length]
}

/**
 * A category-themed, brand-colored illustrated panel standing in for a
 * product photo -- self-contained (no external image hosting, no real
 * brand photography/logos), but distinct per product rather than just per
 * category: the icon shape comes from `category`, the accent color and
 * wordmark come from the product's brand (the first word of `name`).
 */
export function ProductImage({ category, name, className = '' }: ProductImageProps) {
  const art = CATEGORY_ART[category] ?? DEFAULT_ART
  const brand = name ? brandOf(name) : ''
  const palette = paletteFor(brand)
  return (
    <div className={`flex flex-col items-center justify-center gap-1.5 bg-linear-to-br ${palette.bg} ${className}`}>
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" className={`h-1/3 w-1/3 ${palette.text}`}>
        {art.icon}
      </svg>
      {brand && <span className={`text-xs font-bold tracking-tight ${palette.text} opacity-80`}>{brand}</span>}
    </div>
  )
}
