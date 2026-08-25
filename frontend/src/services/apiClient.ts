/**
 * Centralized AgentPay API client (plan.md Section 20).
 *
 * Every service module (transactionApi, auditApi, consoleApi) calls
 * `apiGet()` here rather than using `fetch()` directly, so base URL, JSON
 * parsing, error handling, and timeouts live in exactly one place.
 */
import { API_BASE_URL } from '../lib/constants'

const DEFAULT_TIMEOUT_MS = 10_000

/** The `error` object inside a failed API response (backend/app/schemas/common.py ApiError). */
export interface ApiErrorBody {
  code: string
  message: string
  terminal: boolean
  retryable: boolean
  audit_event_id?: string | null
}

/**
 * Thrown for any failed AgentPay API call -- a `{success: false}` envelope,
 * a network failure, or a request timeout. Carries the same reason code
 * vocabulary the backend uses (app.policy.reason_codes), so callers can
 * branch on `error.code` rather than parsing prose.
 */
export class ApiRequestError extends Error {
  code: string
  terminal: boolean
  retryable: boolean

  constructor(body: ApiErrorBody) {
    super(`${body.code}: ${body.message}`)
    this.name = 'ApiRequestError'
    this.code = body.code
    this.terminal = body.terminal
    this.retryable = body.retryable
  }
}

/**
 * GET an AgentPay REST endpoint and unwrap its `{success, data}` /
 * `{success, error}` envelope.
 *
 * @param path - Request path relative to the API base URL, e.g. "/api/console/summary".
 * @returns The unwrapped `data` payload, typed as `T`.
 * @throws ApiRequestError on a non-2xx response, a `{success: false}` body,
 *   a network failure, or a timeout (10s).
 */
export async function apiGet<T>(path: string): Promise<T> {
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), DEFAULT_TIMEOUT_MS)

  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, { signal: controller.signal })
  } catch (err) {
    const aborted = err instanceof DOMException && err.name === 'AbortError'
    throw new ApiRequestError({
      code: aborted ? 'REQUEST_TIMEOUT' : 'NETWORK_ERROR',
      message: aborted ? 'The request timed out.' : 'Could not reach the AgentPay backend.',
      terminal: true,
      retryable: true,
    })
  } finally {
    clearTimeout(timeoutId)
  }

  const body = await response.json()
  if (!body.success) {
    throw new ApiRequestError(body.error as ApiErrorBody)
  }
  return body.data as T
}
