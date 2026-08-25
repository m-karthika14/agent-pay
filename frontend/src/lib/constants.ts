/**
 * Shared constants for the AgentPay frontend.
 *
 * VITE_API_BASE_URL points at the FastAPI backend (see frontend/.env.example);
 * every service module reads it through here rather than `import.meta.env`
 * directly, so there is exactly one place that knows the env var's name.
 */
export const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'
