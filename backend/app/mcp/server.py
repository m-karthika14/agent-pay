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
from starlette.applications import Starlette

from app.core.config import get_settings

settings = get_settings()

mcp = MCPServer(
    name=settings.mcp_server_name,
    instructions=(
        "AgentPay merchant MCP server. Exposes UrbanNest's catalog and "
        "commerce flow (search, cart, checkout) to external AI buyer "
        "agents. All financial authorization is enforced deterministically "
        "server-side -- tool calls that violate a signed mandate or fail a "
        "hard check return an error; no tool call can bypass AgentPay's "
        "policy engine."
    ),
)


def get_mcp_asgi_app() -> Starlette:
    """
    Register all six commerce tools onto `mcp` and return its Streamable
    HTTP ASGI app, ready to mount.

    Returns:
        A Starlette app implementing the MCP Streamable HTTP transport at
        its root path. app.main mounts this under "/mcp", so combined with
        streamable_http_path="/" here, the final public path is exactly
        "/mcp" (matching MCP_PUBLIC_URL's convention, plan.md Section 17).
    """
    from app.mcp.tools import register_tools

    register_tools(mcp)
    return mcp.streamable_http_app(streamable_http_path="/")
