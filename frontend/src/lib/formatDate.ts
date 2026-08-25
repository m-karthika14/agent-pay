/**
 * Format an ISO timestamp string (as returned by every AgentPay API
 * response) into a short, human-readable local date/time for display.
 */
export function formatDate(isoTimestamp: string): string {
  return new Date(isoTimestamp).toLocaleString()
}
