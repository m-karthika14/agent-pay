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
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import carts, health, products
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.schemas.common import ApiError, ApiErrorResponse, AgentPayError

configure_logging()
logger = logging.getLogger("agentpay")

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """Log startup/shutdown, for demo/ops visibility."""
    logger.info("AgentPay backend started (env=%s)", settings.app_env)
    yield
    logger.info("AgentPay backend shutting down")


app = FastAPI(title=settings.app_name, lifespan=lifespan)

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
