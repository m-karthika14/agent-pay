/**
 * Centralized AgentPay API client (plan.md Section 20).
 *
 * Every service module (productApi, cartApi, mandateApi, checkoutApi,
 * transactionApi, auditApi, consoleApi) calls the functions here rather
 * than using `fetch()` directly, so base URL, JSON parsing, error
 * handling, and timeouts live in exactly one place.
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
 * Call an AgentPay REST endpoint and unwrap its `{success, data}` /
 * `{success, error}` envelope. Shared by apiGet/apiPost/apiPatch/apiDelete
 * so the fetch/timeout/error-handling logic lives in exactly one place.
 *
 * @throws ApiRequestError on a non-2xx response, a `{success: false}` body,
 *   a network failure, or a timeout (10s).
 */
async function apiRequest<T>(path: string, method: string, body?: unknown): Promise<T> {
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), DEFAULT_TIMEOUT_MS)

  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method,
      signal: controller.signal,
      headers: body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    })
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

  const responseBody = await response.json()
  if (!responseBody.success) {
    throw new ApiRequestError(responseBody.error as ApiErrorBody)
  }
  return responseBody.data as T
}

/** GET an AgentPay REST endpoint. @param path - Request path relative to the API base URL. */
export function apiGet<T>(path: string): Promise<T> {
  return apiRequest<T>(path, 'GET')
}

/** POST a JSON body to an AgentPay REST endpoint. */
export function apiPost<T>(path: string, body: unknown = {}): Promise<T> {
  return apiRequest<T>(path, 'POST', body)
}

/** PATCH a JSON body to an AgentPay REST endpoint. */
export function apiPatch<T>(path: string, body: unknown = {}): Promise<T> {
  return apiRequest<T>(path, 'PATCH', body)
}

/** PUT a JSON body to an AgentPay REST endpoint. */
export function apiPut<T>(path: string, body: unknown = {}): Promise<T> {
  return apiRequest<T>(path, 'PUT', body)
}

/** DELETE an AgentPay REST endpoint. */
export function apiDelete<T>(path: string): Promise<T> {
  return apiRequest<T>(path, 'DELETE')
}
