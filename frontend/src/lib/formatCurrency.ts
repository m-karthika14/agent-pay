/**
 * Format an amount stored in minor currency units (e.g. paise for INR --
 * see plan.md Section 8.3 "all money is stored in the smallest currency
 * unit") as a human-readable currency string, e.g. `249900` + `"INR"` ->
 * "₹2,499.00".
 */
export function formatCurrency(amountMinor: number, currency: string): string {
  const amount = amountMinor / 100
  try {
    return new Intl.NumberFormat('en-IN', { style: 'currency', currency }).format(amount)
  } catch {
    // Intl.NumberFormat throws on an unrecognized currency code -- fall back
    // to a plain, still-correct representation rather than crashing the page.
    return `${amount.toFixed(2)} ${currency}`
  }
}
