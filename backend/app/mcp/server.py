"""
Purpose: The AgentPay MCP server instance (plan.md Section 17).

Responsibilities:
- Construct the single MCPServer instance every tool in app.mcp.tools
  registers against.
- Expose get_mcp_asgi_app(), which triggers tool registration and returns
  the Starlette ASGI app to mount into the main FastAPI app (app.main).

Uses the current MCP Python SDK v2 line (`mcp.server.mcpserver.MCPServer`,
the v2 successor to the older v1 `FastMCP` class) rather than an outdated
v1-era tutorial API, per plan.md Section 3.4.
"""
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette

from app.core.config import get_settings

settings = get_settings()

mcp = MCPServer(
    name=settings.mcp_server_name,
    instructions=(
        "AgentPay merchant MCP server. Exposes multiple AI-transactable "
        "merchants' catalogs and a shared commerce flow (search, cart, "
        "checkout) to external AI buyer agents -- call search_products() "
        "with no merchant argument to search every merchant at once (e.g. "
        "to compare prices across merchants), or pass a specific merchant "
        "slug once you know which one to shop. If you know the buyer's "
        "user_id (they told you earlier in conversation), pass it to "
        "search_products()/get_product() too -- it makes your browsing show "
        "up live in their own AgentPay activity popup, purely a transparency "
        "nicety, never required. If you don't already have a mandate_id, "
        "create a cart, add what you intend to buy, then call "
        "request_authorization() and poll check_authorization_status() -- "
        "a human must Approve in the AgentPay app before you get a real "
        "mandate_id; never assume approval. Once approved, you can call "
        "request_checkout() with just the cart_id -- AgentPay already knows "
        "which mandate authorizes it and resolves it for you. All financial authorization "
        "is enforced deterministically server-side -- tool calls that "
        "violate a signed mandate or fail a hard check return an error; no "
        "tool call can bypass AgentPay's policy engine, and you can never "
        "sign a mandate yourself."
    ),
)

# The single fixed Render hostname this backend is deployed at. Kept as an
# explicit literal (not derived from Settings.backend_url) because
# allowed_hosts below is a DNS-rebinding allowlist: if that setting were
# ever left at its localhost default on the deployed service (an easy env
# var to forget -- see Settings.backend_url's own default), every MCP
# request would start failing with "Invalid Host header" again, silently.
# A literal here can't be forgotten the same way.
_RENDER_BACKEND_HOSTNAME = "agentpay-backend-wd5u.onrender.com"


def _mcp_transport_security() -> TransportSecuritySettings:
    """
    DNS-rebinding protection settings for the MCP Streamable HTTP transport
    (plan.md Section 17).

    The MCP SDK validates every request's Host/Origin header against an
    allowlist before it reaches any tool -- its own default only allows
    localhost, which rejects every request once this server is deployed
    anywhere else (observed live: Render's hostname got HTTP 421 "Invalid
    Host header"). allowed_hosts is *who a client dialed* to reach /mcp
    (the backend's own hostname); allowed_origins is *where a browser-based
    caller says it's calling from* -- reused from CORS_ORIGINS (the same
    trusted-frontend list CORSMiddleware already enforces in app.main) so
    there's one source of truth for "which frontends AgentPay trusts", not
    two lists to keep in sync. Server-to-server MCP clients (e.g. Claude's
    connector) typically send no Origin header at all, which the SDK's own
    validator already treats as trivially valid -- allowed_origins mainly
    matters if a browser ever calls this endpoint directly.

    enable_dns_rebinding_protection is left at its default (True) --
    disabling it globally would accept requests claiming to be any host at
    all, which is exactly the class of attack this setting exists to stop.
    """
    allowed_origins = [origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()]
    return TransportSecuritySettings(
        allowed_hosts=[
            "localhost",
            "localhost:*",
            "127.0.0.1",
            "127.0.0.1:*",
            _RENDER_BACKEND_HOSTNAME,
            f"{_RENDER_BACKEND_HOSTNAME}:*",
        ],
        allowed_origins=allowed_origins,
    )


def get_mcp_asgi_app() -> Starlette:
    """
    Register all eight commerce tools onto `mcp` and return its Streamable
    HTTP ASGI app, ready to mount.

    Returns:
        A Starlette app implementing the MCP Streamable HTTP transport at
        its root path. app.main mounts this under "/mcp", so combined with
        streamable_http_path="/" here, the final public path is exactly
        "/mcp" (matching MCP_PUBLIC_URL's convention, plan.md Section 17).
    """
    from app.mcp.tools import register_tools

    register_tools(mcp)
    return mcp.streamable_http_app(streamable_http_path="/", transport_security=_mcp_transport_security())
