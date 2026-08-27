/**
 * Which category AgentPay considers a natural, closely-related add-on for a
 * given purchase category -- e.g. buying wireless earbuds (audio) makes a
 * protective case (accessories) a sensible pairing, but a power bank
 * (power) is not. Deliberately simple and static: this catalog only has one
 * real cross-cutting "add-on" category (accessories), so every primary
 * category maps to it, and accessories itself has no further add-on.
 *
 * Purely a UI convenience for deriving the authorization popup's default
 * "Allow relevant add-ons" toggle -- the actual security boundary is still
 * enforced server-side (policy/checks.py::check_category) against whatever
 * allowed_categories ends up signed into the mandate, completely
 * independent of this map.
 */
const RELATED_CATEGORIES: Record<string, string[]> = {
  audio: ['accessories'],
  wearables: ['accessories'],
  power: ['accessories'],
  accessories: [],
}

/** The related/add-on categories for a set of primary (already-in-cart) categories, excluding anything already primary. */
export function relatedCategoriesFor(primaryCategories: string[]): string[] {
  const related = new Set<string>()
  for (const category of primaryCategories) {
    for (const candidate of RELATED_CATEGORIES[category] ?? []) {
      if (!primaryCategories.includes(candidate)) related.add(candidate)
    }
  }
  return [...related]
}
