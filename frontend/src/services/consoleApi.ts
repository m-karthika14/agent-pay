/**
 * API functions for the Merchant Console's overview panel
 * (plan.md Section 18 — Evaluation/console).
 */
import { apiGet } from './apiClient'
import type { AuditEventRecord } from '../types/audit'
import type { ConsoleMetricsResponse, ConsoleSummaryResponse } from '../types/console'

/** Fetch aggregate transaction/mandate/audit counts plus recent activity. */
export function getConsoleSummary(): Promise<ConsoleSummaryResponse> {
  return apiGet<ConsoleSummaryResponse>('/api/console/summary')
}

/** Fetch the most recent audit events system-wide (a live decision feed), newest first. */
export function getConsoleEvents(limit = 25): Promise<AuditEventRecord[]> {
  return apiGet<AuditEventRecord[]>(`/api/console/events?limit=${limit}`)
}

/** Fetch the Phase 10 evaluation report (Cap-only vs Intent-aware ceiling drift, etc.), if run. */
export function getConsoleMetrics(): Promise<ConsoleMetricsResponse> {
  return apiGet<ConsoleMetricsResponse>('/api/console/metrics')
}
