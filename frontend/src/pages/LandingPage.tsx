import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { AutomaticPaymentSettings } from '../components/AutomaticPaymentSettings'
import { BudgetSettings } from '../components/BudgetSettings'
import { useBuyer } from '../context/BuyerContext'
import { useMerchants } from '../hooks/useMerchants'
import { getMerchantTheme } from '../lib/merchantTheme'

/* ------------------------------------------------------------------ *
 * Icons — a small inline set (Lucide-style, 24px, currentColor stroke)
 * so the page carries no emoji.
 * ------------------------------------------------------------------ */

type IconName =
  | 'shield'
  | 'shield-check'
  | 'card'
  | 'search'
  | 'cart'
  | 'user-check'
  | 'checklist'
  | 'filter'
  | 'lock'
  | 'file'
  | 'repeat'
  | 'check-circle'
  | 'bag'
  | 'trending-up'
  | 'eye'
  | 'crop'
  | 'store'

const ICON_PATHS: Record<IconName, ReactNode> = {
  shield: <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z" />,
  'shield-check': (
    <>
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z" />
      <path d="m9 12 2 2 4-4" />
    </>
  ),
  card: (
    <>
      <rect x="2.5" y="5" width="19" height="14" rx="2" />
      <path d="M2.5 10h19" />
    </>
  ),
  search: (
    <>
      <circle cx="11" cy="11" r="7" />
      <path d="m20 20-4.3-4.3" />
    </>
  ),
  cart: (
    <>
      <circle cx="9" cy="20" r="1.5" />
      <circle cx="18" cy="20" r="1.5" />
      <path d="M3 4h2l2.4 12.3a1 1 0 0 0 1 .7h9.2a1 1 0 0 0 1-.8L21 7H6" />
    </>
  ),
  'user-check': (
    <>
      <path d="M16 21v-2a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4v2" />
      <circle cx="9.5" cy="7" r="4" />
      <path d="m16.5 11 2 2 4-4" />
    </>
  ),
  checklist: (
    <>
      <rect x="3" y="3" width="18" height="18" rx="2" />
      <path d="m8 11.5 2.5 2.5L16 9" />
    </>
  ),
  filter: <path d="M3 4h18l-7 8v6l-4 2v-8L3 4Z" />,
  lock: (
    <>
      <rect x="3.5" y="11" width="17" height="10" rx="2" />
      <path d="M7.5 11V7a4.5 4.5 0 0 1 9 0v4" />
    </>
  ),
  file: (
    <>
      <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8Z" />
      <path d="M14 3v5h5" />
      <path d="M9 13h6M9 17h6" />
    </>
  ),
  repeat: (
    <>
      <path d="m17 2 4 4-4 4" />
      <path d="M3 11V9a4 4 0 0 1 4-4h14" />
      <path d="m7 22-4-4 4-4" />
      <path d="M21 13v2a4 4 0 0 1-4 4H3" />
    </>
  ),
  'check-circle': (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="m8.5 12 2.5 2.5 5-5" />
    </>
  ),
  bag: (
    <>
      <path d="M6 2 4 6v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V6l-2-4Z" />
      <path d="M4 6h16" />
      <path d="M16 10a4 4 0 0 1-8 0" />
    </>
  ),
  'trending-up': (
    <>
      <path d="m3 17 6-6 4 4 8-8" />
      <path d="M17 7h4v4" />
    </>
  ),
  eye: (
    <>
      <path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12Z" />
      <circle cx="12" cy="12" r="3" />
    </>
  ),
  crop: (
    <>
      <path d="M6 2v14a2 2 0 0 0 2 2h14" />
      <path d="M18 22V8a2 2 0 0 0-2-2H2" />
    </>
  ),
  store: (
    <>
      <path d="M4 9h16v10a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V9Z" />
      <path d="m2 9 2-5h16l2 5" />
      <path d="M9 20v-5h6v5" />
    </>
  ),
}

function Icon({ name, className = 'h-5 w-5' }: { name: IconName; className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden
    >
      {ICON_PATHS[name]}
    </svg>
  )
}

/* ------------------------------------------------------------------ *
 * Purchase pipeline — the flow AgentPay actually runs, phase by phase.
 * ------------------------------------------------------------------ */

interface PipelineStep {
  icon: IconName
  title: string
  body: string
  /** Subtly emphasise this step — used for the merchant-agent / Intent-Gate moment. */
  highlight?: boolean
}

interface PipelinePhase {
  key: string
  label: string
  accent: string
  dot: string
  chip: string
  steps: PipelineStep[]
}

const PIPELINE: PipelinePhase[] = [
  {
    key: 'boundary',
    label: 'The buyer sets the boundary',
    accent: 'text-indigo-600',
    dot: 'bg-indigo-500',
    chip: 'bg-indigo-50 text-indigo-600 ring-indigo-100',
    steps: [
      {
        icon: 'shield',
        title: 'Spending mandate',
        body: 'Category, amount cap, and how long it lasts. The one thing that actually authorizes a purchase.',
      },
      {
        icon: 'card',
        title: 'Automatic payments',
        body: 'A reusable payment method, authorized once and capped per transaction, so an approved cart can settle unattended.',
      },
    ],
  },
  {
    key: 'shop',
    label: 'The buyer agent shops',
    accent: 'text-violet-600',
    dot: 'bg-violet-500',
    chip: 'bg-violet-50 text-violet-600 ring-violet-100',
    steps: [
      {
        icon: 'search',
        title: 'Search & compare',
        body: 'Any external AI buyer queries the merchant catalog over MCP and picks the best match on price, category, and stock.',
      },
      {
        icon: 'cart',
        title: 'Build the cart',
        body: 'It assembles exactly what was asked for and brings it back for a decision — nothing is bought yet.',
      },
      {
        icon: 'user-check',
        title: 'Request approval',
        body: 'A real Approve / Edit / Reject request surfaces in the app, not a line in a chat.',
      },
    ],
  },
  {
    key: 'enforce',
    label: 'AgentPay enforces',
    accent: 'text-emerald-600',
    dot: 'bg-emerald-500',
    chip: 'bg-emerald-50 text-emerald-600 ring-emerald-100',
    steps: [
      {
        icon: 'shield-check',
        title: 'Mandate signed & verified',
        body: 'Ed25519 signature, replay-checked, and bound to this exact cart.',
      },
      {
        icon: 'checklist',
        title: 'Deterministic hard checks',
        body: 'Amount cap, allowed category, and cart-hash integrity — enforced by code, before any model runs.',
      },
      {
        icon: 'filter',
        title: 'Merchant agent proposes → Intent Gate decides',
        body: 'The merchant’s revenue agent can propose an upsell or bundle on the cart. An LLM checks it against the mandate and returns allow, block, or escalate — it can only subtract permission.',
        highlight: true,
      },
      {
        icon: 'lock',
        title: 'Cart frozen & re-validated',
        body: 'The precise cart that was authorized is locked and checked once more.',
      },
    ],
  },
  {
    key: 'settle',
    label: 'Payment settles',
    accent: 'text-amber-600',
    dot: 'bg-amber-500',
    chip: 'bg-amber-50 text-amber-600 ring-amber-100',
    steps: [
      {
        icon: 'file',
        title: 'Razorpay order created',
        body: 'A real test-mode order for the frozen cart total.',
      },
      {
        icon: 'repeat',
        title: 'Charge',
        body: 'Automatically against the authorized method when the payment rail supports it — otherwise a one-time authenticated checkout, without breaking the order.',
      },
      {
        icon: 'check-circle',
        title: 'Captured & recorded',
        body: 'Payment captured, order completed, every step written to a hash-chained audit log.',
      },
    ],
  },
]

const THE_BAR = [
  {
    icon: 'eye' as IconName,
    title: 'Traceable',
    body: 'Every money action is a signed entry in a hash-chained audit log that can be replayed and verified.',
  },
  {
    icon: 'crop' as IconName,
    title: 'Controlled',
    body: 'Amount, category, and time are fixed by the buyer’s mandate before any agent runs.',
  },
  {
    icon: 'shield-check' as IconName,
    title: 'Authorized',
    body: 'Deterministic code checks each constraint, and a failed automatic charge falls back gracefully instead of failing the order.',
  },
]

/** AgentPay's dashboard: the problem it addresses, the full purchase pipeline, the buyer's active mandate, and the merchants an AI buyer can shop. */
export function LandingPage() {
  const { userId, name, logout } = useBuyer()
  const { data: merchants, loading, error } = useMerchants()

  return (
    <div className="space-y-16 pb-12">
      {/* ---- Hero ---- */}
      <section className="relative overflow-hidden rounded-3xl border border-slate-200 bg-white px-6 py-14 shadow-sm sm:px-12">
        <div aria-hidden className="pointer-events-none absolute -top-24 -right-20 h-72 w-72 rounded-full bg-indigo-200/40 blur-3xl" />
        <div aria-hidden className="pointer-events-none absolute -bottom-28 -left-24 h-72 w-72 rounded-full bg-violet-200/40 blur-3xl" />

        <div className="relative mx-auto max-w-2xl space-y-5 text-center">
          <span className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-medium text-slate-500">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
            Agentic E-commerce
          </span>

          <h1 className="text-3xl font-bold tracking-tight text-balance text-slate-900 sm:text-4xl">
            AI Shops. Merchants Sell.
            <br />
            <span className="bg-linear-to-r from-indigo-600 to-violet-600 bg-clip-text text-transparent">
              AgentPay Keeps Everyone in Check.
            </span>
          </h1>

          <p className="mx-auto max-w-xl text-base leading-relaxed text-slate-500">
            A buyer agent shops autonomously while a merchant revenue agent finds relevant upsells and bundles.
            AgentPay enforces the buyer’s spending mandate and validates every transaction before a rupee moves.
          </p>

          {userId ? (
            <div className="space-y-4 pt-2">
              <div className="flex items-center justify-center gap-2 text-sm text-slate-500">
                Signed in as <span className="font-medium text-slate-800">{name}</span>
                <button
                  type="button"
                  onClick={logout}
                  className="text-slate-400 underline underline-offset-2 hover:text-slate-600"
                >
                  Log out
                </button>
              </div>

              <div className="mx-auto flex max-w-lg flex-col items-center gap-3 rounded-2xl border border-slate-200 bg-slate-50/80 p-5">
                <p className="text-xs font-semibold tracking-wider text-slate-400 uppercase">Your active mandate</p>
                <BudgetSettings userId={userId} />
                <AutomaticPaymentSettings userId={userId} />
              </div>
            </div>
          ) : (
            <div className="pt-2">
              <Link
                to="/login"
                className="inline-flex items-center gap-2 rounded-xl bg-slate-900 px-6 py-3 text-sm font-semibold text-white shadow-sm transition hover:bg-slate-800"
              >
                Log in to set a mandate
                <span aria-hidden>→</span>
              </Link>
            </div>
          )}
        </div>
      </section>

      {/* ---- Where this is heading ---- */}
      <section className="mx-auto max-w-3xl space-y-6">
        <header className="text-center">
          <h2 className="text-2xl font-bold tracking-tight text-slate-900">Where this is heading</h2>
        </header>

        <div className="space-y-4 text-sm leading-relaxed text-slate-600">
          <p>
            AI agents are starting to shop and pay for people. New protocols — UAP, ACP, AP2, x402 — make it easy for
            them to find products and complete a purchase.
          </p>
          <p>
            But a buyer agent pushes for the cheapest cart, and a merchant agent pushes for a bigger one. Nothing in
            that exchange guarantees the result is what the shopper actually wanted — or allowed.
          </p>
        </div>

        <div className="rounded-2xl border border-slate-200 bg-slate-50/80 p-5 text-sm leading-relaxed text-slate-700">
          <span className="font-semibold text-slate-900">AgentPay is a security and authorization layer</span> between
          AI agents and payments. Any external AI buyer can shop a merchant, while every purchase stays inside the
          buyer’s spending limit, allowed categories, and original intent. If the merchant agent suggests an upsell,
          AgentPay decides whether it’s allowed — before any money moves.
        </div>
      </section>

      {/* ---- Two agents ---- */}
      <section className="mx-auto max-w-3xl">
        <header className="mb-6 text-center">
          <h2 className="text-2xl font-bold tracking-tight text-slate-900">Two agents, opposite incentives</h2>
        </header>

        <div className="grid items-stretch gap-4 sm:grid-cols-[1fr_1.1fr_1fr]">
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="flex items-center gap-3">
              <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-violet-50 text-violet-600 ring-1 ring-violet-100">
                <Icon name="bag" className="h-4.5 w-4.5" />
              </span>
              <h3 className="text-sm font-semibold text-slate-800">Buyer agent</h3>
            </div>
            <p className="mt-3 text-sm leading-relaxed text-slate-500">
              Works for the shopper. Any external AI agent — searches merchants, compares prices, assembles a cart
              against the shopper’s brief.
            </p>
          </div>

          <div className="flex flex-col justify-center rounded-2xl border border-slate-300 bg-slate-900 p-5 text-center shadow-sm">
            <span className="mx-auto flex h-9 w-9 items-center justify-center rounded-xl bg-white/10 text-white">
              <Icon name="shield-check" className="h-4.5 w-4.5" />
            </span>
            <h3 className="mt-3 text-sm font-semibold text-white">AgentPay is the boundary</h3>
            <p className="mt-2 text-sm leading-relaxed text-slate-300">
              The merchant agent can propose; the intent gate and deterministic checks decide. An LLM never grants
              authority.
            </p>
          </div>

          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="flex items-center gap-3">
              <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-amber-50 text-amber-600 ring-1 ring-amber-100">
                <Icon name="trending-up" className="h-4.5 w-4.5" />
              </span>
              <h3 className="text-sm font-semibold text-slate-800">Merchant revenue agent</h3>
            </div>
            <p className="mt-3 text-sm leading-relaxed text-slate-500">
              Works for the store. Proposes upsells and bundles on the frozen cart to grow order value — advisory
              only, never applied on its own.
            </p>
          </div>
        </div>
      </section>

      {/* ---- Purchase pipeline ---- */}
      <section className="mx-auto max-w-3xl">
        <header className="mb-10 text-center">
          <h2 className="text-2xl font-bold tracking-tight text-slate-900">How a purchase flows</h2>
          <p className="mt-2 text-sm text-slate-500">From the limit the buyer sets to a settled, fully audited order.</p>
        </header>

        <div className="space-y-9">
          {PIPELINE.map((phase) => (
            <div key={phase.key}>
              <div className="mb-4 flex items-center gap-2">
                <span className={`h-2 w-2 rounded-full ${phase.dot}`} />
                <h3 className={`text-xs font-semibold tracking-wider uppercase ${phase.accent}`}>{phase.label}</h3>
              </div>

              <ol className="space-y-3">
                {phase.steps.map((step, idx) => (
                  <li key={step.title} className="flex gap-4">
                    <div className="flex flex-col items-center">
                      <span
                        className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ring-1 ${phase.chip}`}
                      >
                        <Icon name={step.icon} className="h-5 w-5" />
                      </span>
                      {idx < phase.steps.length - 1 && <span className="mt-1 w-px flex-1 bg-slate-200" />}
                    </div>

                    <div
                      className={`flex-1 rounded-2xl border px-4 py-3 shadow-sm transition ${
                        step.highlight
                          ? 'border-emerald-200 bg-emerald-50/60 ring-1 ring-emerald-100 hover:shadow-md'
                          : 'border-slate-200 bg-white hover:border-slate-300 hover:shadow-md'
                      }`}
                    >
                      <p className="text-sm font-semibold text-slate-800">{step.title}</p>
                      <p className="mt-0.5 text-sm leading-relaxed text-slate-500">{step.body}</p>
                    </div>
                  </li>
                ))}
              </ol>
            </div>
          ))}
        </div>
      </section>

      {/* ---- The bar ---- */}
      <section className="mx-auto max-w-3xl">
        <header className="mb-6 text-center">
          <h2 className="text-2xl font-bold tracking-tight text-slate-900">The bar</h2>
          <p className="mt-2 text-sm text-slate-500">Every money action: traceable, controlled, authorized.</p>
        </header>

        <div className="grid gap-4 sm:grid-cols-3">
          {THE_BAR.map((item) => (
            <div key={item.title} className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-slate-100 text-slate-600">
                <Icon name={item.icon} className="h-4.5 w-4.5" />
              </span>
              <p className="mt-3 text-sm font-semibold text-slate-800">{item.title}</p>
              <p className="mt-1 text-sm leading-relaxed text-slate-500">{item.body}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ---- Core rule ---- */}
      <section className="mx-auto max-w-3xl rounded-2xl bg-slate-900 px-6 py-8 text-center">
        <p className="text-xs font-semibold tracking-wider text-slate-400 uppercase">The core rule</p>
        <p className="mt-3 text-2xl font-bold tracking-tight text-white">AI can suggest. Code decides.</p>
        <p className="mx-auto mt-3 max-w-xl text-sm leading-relaxed text-slate-300">
          LLMs may propose, revise, block, or escalate — but they can never grant spending authority. Every hard
          limit is enforced by deterministic code.
        </p>
      </section>

      {/* ---- Merchants ---- */}
      <section className="mx-auto max-w-3xl">
        <header className="mb-6 text-center">
          <h2 className="text-2xl font-bold tracking-tight text-slate-900">Merchants an AI buyer can shop</h2>
          <p className="mt-2 text-sm text-slate-500">Exposed as an agent-readable catalog over MCP.</p>
        </header>

        {loading && <p className="text-center text-sm text-slate-500">Loading merchants…</p>}
        {error && <p className="text-center text-sm text-red-600">{error.message}</p>}

        {merchants && (
          <div className="grid gap-4 sm:grid-cols-2">
            {merchants.map((merchant) => {
              const theme = getMerchantTheme(merchant.slug)
              return (
                <div
                  key={merchant.merchant_id}
                  className="group overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm transition hover:-translate-y-0.5 hover:shadow-lg"
                >
                  <div className={`h-1.5 bg-linear-to-r ${theme.navGradient}`} />
                  <div className="flex items-center gap-4 p-5">
                    <span className={`flex h-12 w-12 items-center justify-center rounded-xl bg-slate-50 ${theme.accentText}`}>
                      <Icon name="store" className="h-6 w-6" />
                    </span>
                    <div className="min-w-0">
                      <h3 className="truncate text-base font-semibold text-slate-900">{merchant.name}</h3>
                      <p className="text-xs tracking-wide text-slate-400 uppercase">Electronics</p>
                    </div>
                  </div>
                  {userId && (
                    <Link
                      to={`/store/${merchant.slug}`}
                      className="flex items-center justify-between border-t border-slate-100 px-5 py-3 text-sm font-medium text-slate-500 transition group-hover:text-slate-800"
                    >
                      Browse catalog
                      <span aria-hidden>→</span>
                    </Link>
                  )}
                </div>
              )
            })}
          </div>
        )}

        {!userId && (
          <p className="mt-4 text-center text-xs text-slate-400">Log in to connect an agent to these merchants.</p>
        )}
      </section>
    </div>
  )
}
