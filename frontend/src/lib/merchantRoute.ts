/**
 * Every merchant-scoped storefront page lives under /store/:merchantSlug/...
 * Components that sit outside that route's own subtree (Navbar, CartContext
 * -- both rendered by the shared AppLayout, not by a /store/:merchantSlug
 * route itself) can't read the slug via useParams(), so they derive it from
 * the URL directly instead.
 */
export function merchantSlugFromPath(pathname: string): string | null {
  return pathname.match(/^\/store\/([^/]+)/)?.[1] ?? null
}
