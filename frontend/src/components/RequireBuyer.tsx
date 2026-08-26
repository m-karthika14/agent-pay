import { Navigate, useLocation } from 'react-router-dom'
import type { ReactNode } from 'react'
import { useBuyer } from '../context/BuyerContext'

/** Redirects to /login if no buyer is logged in yet. Wraps every storefront route that needs a real user_id (cart, checkout, order, history). */
export function RequireBuyer({ children }: { children: ReactNode }) {
  const { userId } = useBuyer()
  const location = useLocation()

  if (!userId) {
    return <Navigate to="/login" state={{ from: location }} replace />
  }
  return <>{children}</>
}
