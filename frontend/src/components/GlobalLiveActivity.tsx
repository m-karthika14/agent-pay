/**
 * Global "watch Claude shop" popup -- automatically shows the buyer's own
 * live activity (their most recent cart, through authorization, checkout,
 * and payment) the moment there's anything to show, with no mandate_id to
 * paste in anywhere. Reuses the exact same LiveConversation component and
 * event-to-message translation the Checkout/AI-Activity pages already use.
 *
 * Suppressed on routes that already embed their own LiveConversation
 * instance (Checkout, and the AI Activity page's own arbitrary-mandate_id
 * viewer) so the two never render on top of each other.
 */
import { useLocation } from 'react-router-dom'
import { LiveConversation } from './LiveConversation'
import { useBuyer } from '../context/BuyerContext'
import { useLiveShoppingActivity } from '../hooks/useLiveShoppingActivity'

const SUPPRESSED_ROUTES = [/^\/store\/[^/]+\/checkout$/, /^\/agent$/]

export function GlobalLiveActivity() {
  const { userId } = useBuyer()
  const location = useLocation()
  const { events, cart } = useLiveShoppingActivity(userId)

  if (SUPPRESSED_ROUTES.some((pattern) => pattern.test(location.pathname))) return null
  if (events.length === 0) return null

  return <LiveConversation events={events} cart={cart} />
}
