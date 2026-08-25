"""
Purpose: AgentPay FastAPI application entry point.

Responsibilities (plan.md Section 45):
- App initialization and startup logging.
- CORS configuration (from Settings.cors_origins).
- Route registration for every api/routes/* router.
- A single exception handler that turns any AgentPayError into the
  standard error envelope (plan.md Section 46), so route handlers never
  need to format error responses by hand.

This module wires things together only — it must never contain business
logic itself.
"""
import logging
from collections.abc import AsyncGenerator
from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import carts, checkout, health, products, transactions, webhooks
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.mcp.server import get_mcp_asgi_app, mcp
from app.schemas.common import ApiError, ApiErrorResponse, AgentPayError

configure_logging()
logger = logging.getLogger("agentpay")

settings = get_settings()

# Built once at import time: registers the six MCP tools (app.mcp.tools)
# and returns the Streamable HTTP ASGI app, mounted below at "/mcp".
mcp_asgi_app = get_mcp_asgi_app()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Log startup/shutdown, and run the MCP session manager for the app's
    lifetime.

    The MCP Streamable HTTP transport's session manager has its own async
    context manager (`mcp.session_manager.run()`) that must be active for
    tool calls to work -- mounting the MCP ASGI app alone does not start it,
    since FastAPI does not automatically propagate a mounted sub-app's own
    lifespan. This is the SDK's documented pattern for combining an
    MCPServer with an existing FastAPI application.
    """
    logger.info("AgentPay backend started (env=%s)", settings.app_env)
    async with AsyncExitStack() as stack:
        await stack.enter_async_context(mcp.session_manager.run())
        yield
    logger.info("AgentPay backend shutting down")


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.mount("/mcp", mcp_asgi_app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(products.router)
app.include_router(carts.router)
app.include_router(checkout.router)
app.include_router(transactions.router)
app.include_router(webhooks.router)


@app.exception_handler(AgentPayError)
async def agentpay_error_handler(request: Request, exc: AgentPayError) -> JSONResponse:
    """
    Convert any AgentPayError raised by a route/service into the standard
    `{"success": false, "error": {...}}` envelope (plan.md Section 46).
    """
    envelope = ApiErrorResponse(
        error=ApiError(
            code=exc.reason_code,
            message=exc.message,
            terminal=exc.terminal,
            retryable=exc.retryable,
        )
    )
    return JSONResponse(status_code=exc.status_code, content=envelope.model_dump())
