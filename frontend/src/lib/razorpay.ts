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
  prefill?: { name?: string; email?: string; contact?: string }
  theme?: { color?: string }
  // 1 marks this Checkout as an e-mandate / recurring-token registration.
  recurring?: 1
  // The Razorpay Customer the registration order was created against;
  // required alongside `recurring` for the token to be reusable.
  customer_id?: string
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
  buyerContact?: string
  storeName: string
  themeColor?: string
  /**
   * When true, this Checkout is the ONE interactive transaction that
   * registers a reusable payment token (Automatic Payments setup). Razorpay
   * only issues an e-mandate / recurring-capable token if Checkout is
   * opened with `recurring: 1` and the `customer_id` the registration order
   * was created against -- without them it runs as a plain one-time
   * payment and the resulting token is rejected by the recurring-charge
   * API ("No db records found.").
   */
  recurring?: boolean
  customerId?: string
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
    name: options.storeName,
    order_id: options.razorpayOrderId,
    prefill: {
      name: options.buyerName,
      email: options.buyerEmail,
      ...(options.buyerContact ? { contact: options.buyerContact } : {}),
    },
    theme: { color: options.themeColor ?? '#0f172a' },
    ...(options.recurring ? { recurring: 1 } : {}),
    ...(options.customerId ? { customer_id: options.customerId } : {}),
    handler: (response) => options.onSuccess(response.razorpay_payment_id),
    modal: { ondismiss: options.onDismiss },
  })
  rzp.on('payment.failed', (response) => options.onFailure(response.error.description))
  rzp.open()
}
