import { useAsync } from './useAsync'
import { getConsoleEvents, getConsoleMetrics, getConsoleSummary } from '../services/consoleApi'
import type { AuditEventRecord } from '../types/audit'
import type { ConsoleMetricsResponse, ConsoleSummaryResponse } from '../types/console'

/** Fetches the console's aggregate summary and exposes loading/error state. */
export function useConsoleSummary() {
  return useAsync<ConsoleSummaryResponse>(() => getConsoleSummary(), [])
}

/** Fetches the console's recent system-wide event feed and exposes loading/error state. */
export function useConsoleEvents(limit = 25) {
  return useAsync<AuditEventRecord[]>(() => getConsoleEvents(limit), [limit])
}

/** Fetches the Phase 10 evaluation metrics report and exposes loading/error state. */
export function useConsoleMetrics() {
  return useAsync<ConsoleMetricsResponse>(() => getConsoleMetrics(), [])
}
