/**
 * Format an ISO timestamp string (as returned by every AgentPay API
 * response) into a short, human-readable local date/time for display.
 */
export function formatDate(isoTimestamp: string): string {
  return new Date(isoTimestamp).toLocaleString()
}

/** Format an ISO timestamp as a short local time only, e.g. "2:31 PM" -- for chat-style message timestamps. */
export function formatTime(isoTimestamp: string): string {
  return new Date(isoTimestamp).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
}
