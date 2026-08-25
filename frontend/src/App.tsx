import { BrowserRouter } from 'react-router-dom'
import { BuyerProvider } from './context/BuyerContext'
import { CartProvider } from './context/CartContext'
import { AppRoutes } from './routes/AppRoutes'

/**
 * Root application composition for AgentPay.
 *
 * Wraps React Router around both the UrbanNest storefront (HomePage,
 * ProductPage, CartPage, CheckoutPage, OrderPage, AgentActivityPage) and
 * the read-only Merchant Console (plan.md Section 19.2), under a shared
 * demo buyer identity + cart state (BuyerProvider/CartProvider) that only
 * the storefront routes actually use.
 */
function App() {
  return (
    <BrowserRouter>
      <BuyerProvider>
        <CartProvider>
          <AppRoutes />
        </CartProvider>
      </BuyerProvider>
    </BrowserRouter>
  )
}

export default App
