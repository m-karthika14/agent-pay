import { useEffect, useRef, useState } from 'react'

interface PollingState<T> {
  data: T | null
  loading: boolean
  error: Error | null
}

const DEFAULT_INTERVAL_MS = 2_000

/**
 * Run an async fetcher on mount and again every `intervalMs`, exposing
 * `{data, loading, error}`. Used by the live "AI Activity" panel to watch a
 * cart/mandate's progress via polling rather than WebSockets/SSE (per
 * plan.md Section 3.9's anti-complexity stance).
 *
 * Unlike useAsync, `loading` only reflects the *first* fetch -- later polls
 * update `data`/`error` in place so the UI doesn't flicker into a loading
 * state every couple of seconds. Pass `enabled: false` to pause polling
 * (e.g. before the caller has anything to watch yet).
 */
export function usePolling<T>(
  fetcher: () => Promise<T>,
  deps: unknown[],
  options: { intervalMs?: number; enabled?: boolean } = {},
): PollingState<T> {
  const { intervalMs = DEFAULT_INTERVAL_MS, enabled = true } = options
  const [state, setState] = useState<PollingState<T>>({ data: null, loading: enabled, error: null })
  const fetcherRef = useRef(fetcher)
  fetcherRef.current = fetcher

  useEffect(() => {
    if (!enabled) {
      setState({ data: null, loading: false, error: null })
      return
    }

    let cancelled = false
    let inFlight = false
    setState({ data: null, loading: true, error: null })

    async function poll() {
      if (inFlight) return
      inFlight = true
      try {
        const data = await fetcherRef.current()
        if (!cancelled) setState({ data, loading: false, error: null })
      } catch (error) {
        if (!cancelled) {
          setState((prev) => ({
            data: prev.data,
            loading: false,
            error: error instanceof Error ? error : new Error(String(error)),
          }))
        }
      } finally {
        inFlight = false
      }
    }

    void poll()
    const id = setInterval(() => void poll(), intervalMs)

    return () => {
      cancelled = true
      clearInterval(id)
    }
    // fetcher intentionally excluded (see fetcherRef above): callers pass a
    // fresh closure each render, so depending on it would restart polling
    // every render instead of only when `deps` actually change.
  }, [enabled, intervalMs, ...deps])

  return state
}
