import { NavLink } from 'react-router-dom'
import { useCart } from '../context/CartContext'

const LINK_CLASS = ({ isActive }: { isActive: boolean }) =>
  `text-sm font-medium ${isActive ? 'text-slate-900' : 'text-slate-500 hover:text-slate-700'}`

/** Top navigation bar: the UrbanNest storefront, the live AI Activity panel, and the Merchant Console. */
export function Navbar() {
  const { itemCount } = useCart()

  return (
    <header className="border-b border-slate-200 bg-white">
      <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-3">
        <NavLink to="/" className="text-sm font-semibold tracking-tight text-slate-900">
          UrbanNest
        </NavLink>
        <nav className="flex items-center gap-5">
          <NavLink to="/" end className={LINK_CLASS}>
            Shop
          </NavLink>
          <NavLink to="/cart" className={LINK_CLASS}>
            Cart{itemCount > 0 ? ` (${itemCount})` : ''}
          </NavLink>
          <NavLink to="/agent" className={LINK_CLASS}>
            AI Activity
          </NavLink>
          <NavLink to="/console" className={LINK_CLASS}>
            Merchant Console
          </NavLink>
        </nav>
      </div>
    </header>
  )
}
