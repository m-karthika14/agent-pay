import { useEffect, useState } from 'react'

interface AsyncState<T> {
  data: T | null
  loading: boolean
  error: Error | null
}

/**
 * Run an async fetcher on mount (and whenever `deps` changes), exposing
 * `{data, loading, error}`. Shared by useTransaction/useAudit/useConsole so
 * each hook only supplies its own fetcher, not its own loading/error
 * bookkeeping (plan.md Section 20/21's hooks pattern).
 */
export function useAsync<T>(fetcher: () => Promise<T>, deps: unknown[]): AsyncState<T> {
  const [state, setState] = useState<AsyncState<T>>({ data: null, loading: true, error: null })

  useEffect(() => {
    let cancelled = false
    setState({ data: null, loading: true, error: null })
    fetcher()
      .then((data) => {
        if (!cancelled) setState({ data, loading: false, error: null })
      })
      .catch((error: unknown) => {
        if (!cancelled) setState({ data: null, loading: false, error: error instanceof Error ? error : new Error(String(error)) })
      })
    return () => {
      cancelled = true
    }
    // fetcher intentionally excluded: callers pass a fresh closure each
    // render, so depending on it would refetch every render instead of
    // only when the caller-supplied `deps` actually change. oxlint's
    // exhaustive-deps check can't see through this generic wrapper (`deps`
    // is a parameter, not a literal array), so it always flags this line;
    // that warning is a known false positive for this pattern.
  }, deps)

  return state
}
