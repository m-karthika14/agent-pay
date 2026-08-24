"""
Purpose: Load and validate all AgentPay environment variables in one place.

Responsibilities:
- Read configuration from the process environment / a local .env file.
- Validate required values with Pydantic so misconfiguration fails fast at
  startup rather than deep inside a request handler.
- Provide a single cached Settings instance (get_settings()) that the rest of
  the codebase depends on.

Per plan.md Section 45, no other module should read `os.environ` directly —
everything goes through Settings so secrets stay centralized and auditable.
"""
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Typed application configuration, sourced from environment variables / .env.

    Field names match the keys documented in .env.example. Secrets (Razorpay
    key secret, webhook secret, Gemini API key, Ed25519 private key, DB
    password embedded in the URL) are only ever read here and passed down
    explicitly — they must never be logged or exposed to the frontend.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Application
    app_env: str = Field(default="development", alias="APP_ENV")
    app_name: str = Field(default="AgentPay", alias="APP_NAME")
    backend_url: str = Field(default="http://localhost:8000", alias="BACKEND_URL")
    frontend_url: str = Field(default="http://localhost:5173", alias="FRONTEND_URL")
    cors_origins: str = Field(default="http://localhost:5173", alias="CORS_ORIGINS")

    # Database
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/agentpay",
        alias="DATABASE_URL",
    )

    # Razorpay Test Mode (not used until Phase 4)
    razorpay_key_id: str = Field(default="", alias="RAZORPAY_KEY_ID")
    razorpay_key_secret: str = Field(default="", alias="RAZORPAY_KEY_SECRET")
    razorpay_webhook_secret: str = Field(default="", alias="RAZORPAY_WEBHOOK_SECRET")

    # Gemini (not used until Phase 6/7)
    gemini_api_key: str = Field(default="", alias="GEMINI_API_KEY")
    gemini_model: str = Field(default="", alias="GEMINI_MODEL")

    # MCP (not used until Phase 5)
    mcp_public_url: str = Field(default="http://localhost:8000/mcp", alias="MCP_PUBLIC_URL")
    mcp_server_name: str = Field(default="AgentPay Merchant MCP", alias="MCP_SERVER_NAME")

    # Mandate signing (Phase 1)
    ed25519_private_key_b64: str = Field(default="", alias="ED25519_PRIVATE_KEY_B64")
    ed25519_public_key_b64: str = Field(default="", alias="ED25519_PUBLIC_KEY_B64")

    # Intent gate (not used until Phase 7)
    intent_confidence_threshold: float = Field(default=0.80, alias="INTENT_CONFIDENCE_THRESHOLD")

    # Audit
    audit_hash_algorithm: str = Field(default="sha256", alias="AUDIT_HASH_ALGORITHM")

    @field_validator("database_url")
    @classmethod
    def _normalize_asyncpg_driver(cls, value: str) -> str:
        """
        Rewrite a plain `postgresql://` URL to `postgresql+asyncpg://`.

        Managed database providers (e.g. Render's `fromDatabase` env var
        linking) hand out a driver-agnostic `postgresql://` connection
        string, but SQLAlchemy's async engine requires the `+asyncpg`
        dialect suffix to be explicit. Normalizing here means deployment
        platforms can link the database URL directly without anyone having
        to hand-edit it into an incompatible format.
        """
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+asyncpg://", 1)
        return value


@lru_cache
def get_settings() -> Settings:
    """
    Return the process-wide Settings instance, constructed once and cached.

    Using lru_cache (rather than a bare module-level singleton) makes it easy
    to override settings in tests via `get_settings.cache_clear()`.
    """
    return Settings()
