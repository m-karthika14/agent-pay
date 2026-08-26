import { NavLink } from 'react-router-dom'
import { useCart } from '../context/CartContext'

const SHOP_TABS = [
  { to: '/', label: 'Shop', end: true },
  { to: '/cart', label: 'Cart' },
  { to: '/history', label: 'Buying History' },
]

const UTILITY_LINK_CLASS = ({ isActive }: { isActive: boolean }) =>
  `text-sm font-medium ${isActive ? 'text-slate-900' : 'text-slate-500 hover:text-slate-700'}`

const TAB_CLASS = ({ isActive }: { isActive: boolean }) =>
  `rounded-full px-3.5 py-1.5 text-sm font-medium transition ${
    isActive ? 'bg-white text-indigo-700 shadow-sm' : 'text-indigo-100 hover:text-white'
  }`

/** Top navigation bar: the UrbanNest storefront's core shopping tabs, plus the live AI Activity panel and Merchant Console. */
export function Navbar() {
  const { itemCount } = useCart()

  return (
    <header className="border-b border-slate-200 bg-white">
      <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-3 px-4 py-3">
        <NavLink to="/" className="text-sm font-semibold tracking-tight text-slate-900">
          UrbanNest
        </NavLink>

        <nav className="flex items-center gap-1 rounded-full bg-linear-to-r from-indigo-600 to-indigo-500 p-1 shadow-inner">
          {SHOP_TABS.map((tab) => (
            <NavLink key={tab.to} to={tab.to} end={tab.end} className={TAB_CLASS}>
              {tab.label === 'Cart' && itemCount > 0 ? `Cart (${itemCount})` : tab.label}
            </NavLink>
          ))}
        </nav>

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
