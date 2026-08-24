"""
Purpose: Shared API response envelope and domain exceptions.

Responsibilities:
- Define the single success/error JSON shape every AgentPay API route uses
  (plan.md Section 46 — API Contract Rules).
- Define a small hierarchy of domain exceptions that carry an HTTP status and
  a stable reason code, so route handlers can `raise` instead of building
  error responses by hand. app.main registers one exception handler that
  turns any AgentPayError into the standard error envelope.

This module has no framework/DB dependency beyond Pydantic, so it can be
imported from any layer without creating import cycles.
"""
from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ApiError(BaseModel):
    """The `error` object inside a failed API response (plan.md Section 46)."""

    code: str
    message: str
    terminal: bool = True
    retryable: bool = False
    audit_event_id: str | None = None


class ApiErrorResponse(BaseModel):
    """Envelope for a failed API response: `{"success": false, "error": {...}}`."""

    success: bool = False
    error: ApiError


class ApiSuccessResponse(BaseModel, Generic[T]):
    """Envelope for a successful API response: `{"success": true, "data": {...}}`."""

    success: bool = True
    data: T


class AgentPayError(Exception):
    """
    Base class for domain errors that should become a structured API error
    response rather than an unhandled 500.

    Args:
        reason_code: Stable machine-readable code (see app.policy.reason_codes
            for policy-driven codes; simpler resource errors define their own
            short code alongside their exception class).
        message: Human-readable explanation, safe to return to API callers.
        status_code: HTTP status to respond with.
        terminal: Whether this error ends the transaction outright (True) or
            is a non-terminal, retryable condition (False).
    """

    def __init__(
        self,
        reason_code: str,
        message: str,
        *,
        status_code: int = 400,
        terminal: bool = True,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.message = message
        self.status_code = status_code
        self.terminal = terminal
        self.retryable = retryable


class NotFoundError(AgentPayError):
    """Raised when a requested resource (product, cart, etc.) does not exist."""

    def __init__(self, reason_code: str, message: str) -> None:
        super().__init__(reason_code, message, status_code=404, terminal=True, retryable=False)


class ValidationError(AgentPayError):
    """Raised when a request is well-formed but violates a business rule."""

    def __init__(self, reason_code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(reason_code, message, status_code=400, terminal=True, retryable=retryable)
