import { Link, NavLink, useLocation } from 'react-router-dom'
import { useBuyer } from '../context/BuyerContext'
import { useCart } from '../context/CartContext'
import { useMerchants } from '../hooks/useMerchants'
import { getMerchantTheme } from '../lib/merchantTheme'
import { merchantSlugFromPath } from '../lib/merchantRoute'

const UTILITY_LINK_CLASS = ({ isActive }: { isActive: boolean }) =>
  `text-sm font-medium ${isActive ? 'text-slate-900' : 'text-slate-500 hover:text-slate-700'}`

/** Top navigation bar: the active merchant's shopping tabs + buyer identity in one card, plus the live AI Activity panel and Merchant Console at the far end. Re-themes and re-links itself to whichever merchant the current /store/:merchantSlug route is under. */
export function Navbar() {
  const { itemCount } = useCart()
  const { userId, name, logout } = useBuyer()
  const { data: merchants } = useMerchants()
  const location = useLocation()
  const merchantSlug = merchantSlugFromPath(location.pathname)
  const theme = getMerchantTheme(merchantSlug)
  const merchantName = merchants?.find((m) => m.slug === merchantSlug)?.name

  const tabClass = ({ isActive }: { isActive: boolean }) =>
    `rounded-full px-3.5 py-1.5 text-sm font-medium transition ${
      isActive ? `bg-white ${theme.navActiveTab} shadow-sm` : 'text-white/80 hover:text-white'
    }`

  return (
    <header className="border-b border-slate-200 bg-white">
      <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-3 px-4 py-3">
        <Link to="/" className="text-sm font-semibold tracking-tight text-slate-900">
          {merchantName ?? 'AgentPay'}
        </Link>

        {merchantSlug && (
          <nav className={`flex items-center gap-1 rounded-full bg-linear-to-r ${theme.navGradient} py-1 pr-1.5 pl-1 shadow-inner`}>
            <NavLink to={`/store/${merchantSlug}`} end className={tabClass}>
              Shop
            </NavLink>
            <NavLink to={`/store/${merchantSlug}/cart`} className={tabClass}>
              {itemCount > 0 ? `Cart (${itemCount})` : 'Cart'}
            </NavLink>
            <NavLink to="/history" className={tabClass}>
              Buying History
            </NavLink>
            {userId && (
              <>
                <span className="mx-1 h-5 w-px bg-white/25" aria-hidden="true" />
                <span className="flex h-7 shrink-0 items-center rounded-full bg-white/20 px-3 text-sm font-medium whitespace-nowrap text-white">
                  {name}
                </span>
                <button
                  type="button"
                  onClick={logout}
                  title="Log out"
                  aria-label="Log out"
                  className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-white/80 transition hover:bg-white/15 hover:text-white"
                >
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="h-4 w-4">
                    <path d="M15 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10" strokeLinecap="round" strokeLinejoin="round" />
                    <path d="M10 12h11M17 8l4 4-4 4" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </button>
              </>
            )}
          </nav>
        )}

        <nav className="flex items-center gap-5">
          <NavLink to="/agent" className={UTILITY_LINK_CLASS}>
            AI Activity
          </NavLink>
          <NavLink to="/console" className={UTILITY_LINK_CLASS}>
            Merchant Console
          </NavLink>
        </nav>
      </div>
    </header>
  )
}
