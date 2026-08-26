import type { ReactNode } from 'react'

interface ProductImageProps {
  category: string
  className?: string
}

interface CategoryArt {
  gradient: string
  iconColor: string
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
  audio: { gradient: "from-violet-100 to-violet-200", iconColor: "text-violet-500", icon: ICONS.audio },
  wearables: { gradient: "from-rose-100 to-rose-200", iconColor: "text-rose-500", icon: ICONS.wearables },
  power: { gradient: "from-amber-100 to-amber-200", iconColor: "text-amber-600", icon: ICONS.power },
  accessories: { gradient: "from-sky-100 to-sky-200", iconColor: "text-sky-500", icon: ICONS.accessories },
}
const DEFAULT_ART: CategoryArt = { gradient: "from-slate-100 to-slate-200", iconColor: "text-slate-400", icon: ICONS.accessories }

/** A category-themed illustrated panel standing in for a product photo -- self-contained (no external image hosting), consistent per category. */
export function ProductImage({ category, className = "" }: ProductImageProps) {
  const art = CATEGORY_ART[category] ?? DEFAULT_ART
  return (
    <div className={`flex items-center justify-center bg-linear-to-br ${art.gradient} ${className}`}>
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" className={`h-1/2 w-1/2 ${art.iconColor}`}>
        {art.icon}
      </svg>
    </div>
  )
}
