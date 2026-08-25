/**
 * Loads Razorpay's Standard Checkout widget script and wraps opening it.
 *
 * The webhook (POST /api/webhooks/razorpay) remains the authoritative
 * completion signal (plan.md Section 22) -- this widget's callbacks only
 * drive UI navigation (to /order/:orderId, which polls for the real
 * outcome), never the transaction's actual recorded status.
 */
const SCRIPT_SRC = 'https://checkout.razorpay.com/v1/checkout.js'

interface RazorpayPaymentResponse {
  razorpay_payment_id: string
  razorpay_order_id: string
  razorpay_signature: string
}

interface RazorpayOptions {
  key: string
  amount: number
  currency: string
  name: string
  order_id: string
  prefill?: { name?: string; email?: string }
  theme?: { color?: string }
  handler: (response: RazorpayPaymentResponse) => void
  modal?: { ondismiss?: () => void }
}

interface RazorpayInstance {
  open: () => void
  on: (event: 'payment.failed', handler: (response: { error: { description: string } }) => void) => void
}

declare global {
  interface Window {
    Razorpay?: new (options: RazorpayOptions) => RazorpayInstance
  }
}

let scriptPromise: Promise<void> | null = null

/** Load the Razorpay Checkout.js script once, reusing the same promise on repeat calls. */
function loadRazorpayScript(): Promise<void> {
  if (window.Razorpay) return Promise.resolve()
  if (scriptPromise) return scriptPromise

  scriptPromise = new Promise((resolve, reject) => {
    const script = document.createElement('script')
    script.src = SCRIPT_SRC
    script.onload = () => resolve()
    script.onerror = () => reject(new Error('Could not load the Razorpay Checkout script.'))
    document.body.appendChild(script)
  })
  return scriptPromise
}

/**
 * Open Razorpay's Standard Checkout widget for an already-created order.
 * `onSuccess`/`onFailure` only affect UI navigation; the webhook is what
 * actually records the payment outcome.
 */
export async function openRazorpayCheckout(options: {
  keyId: string
  razorpayOrderId: string
  amountMinor: number
  currency: string
  buyerName: string
  buyerEmail: string
  onSuccess: (paymentId: string) => void
  onFailure: (reason: string) => void
  onDismiss: () => void
}): Promise<void> {
  await loadRazorpayScript()
  if (!window.Razorpay) throw new Error('Razorpay Checkout script did not load correctly.')

  const rzp = new window.Razorpay({
    key: options.keyId,
    amount: options.amountMinor,
    currency: options.currency,
    name: 'UrbanNest',
    order_id: options.razorpayOrderId,
    prefill: { name: options.buyerName, email: options.buyerEmail },
    theme: { color: '#0f172a' },
    handler: (response) => options.onSuccess(response.razorpay_payment_id),
    modal: { ondismiss: options.onDismiss },
  })
  rzp.on('payment.failed', (response) => options.onFailure(response.error.description))
  rzp.open()
}
