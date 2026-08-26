/**
 * Per-merchant accent theming (plan.md "Visual identity"). Class names are
 * kept as static string literals (never built via `${accent}-600` template
 * interpolation) so Tailwind's build-time class scanner can actually find
 * them -- a dynamically-constructed class name is invisible to it and would
 * silently ship unstyled.
 */
export interface MerchantTheme {
  /** Nav pill wrapper background. */
  navGradient: string
  /** Nav pill's active-tab text color. */
  navActiveTab: string
  /** Primary action buttons (Add to cart, Authorize purchase, etc). */
  primaryButton: string
  /** Category label / small accent text. */
  accentText: string
  /** Card hover border/shadow accent. */
  cardHover: string
  /** Hex color handed to Razorpay's checkout widget `theme.color`. */
  razorpayColor: string
}

const URBANNEST_THEME: MerchantTheme = {
  navGradient: 'from-indigo-600 to-indigo-500',
  navActiveTab: 'text-indigo-700',
  primaryButton: 'bg-indigo-600 hover:bg-indigo-700',
  accentText: 'text-indigo-500',
  cardHover: 'hover:border-indigo-200 hover:shadow-indigo-100',
  razorpayColor: '#4f46e5',
}

const TECHHUB_THEME: MerchantTheme = {
  navGradient: 'from-amber-600 to-amber-500',
  navActiveTab: 'text-amber-700',
  primaryButton: 'bg-amber-600 hover:bg-amber-700',
  accentText: 'text-amber-600',
  cardHover: 'hover:border-amber-200 hover:shadow-amber-100',
  razorpayColor: '#d97706',
}

const THEMES: Record<string, MerchantTheme> = {
  urbannest: URBANNEST_THEME,
  techhub: TECHHUB_THEME,
}

export function getMerchantTheme(slug: string | null | undefined): MerchantTheme {
  return (slug && THEMES[slug]) || URBANNEST_THEME
}
