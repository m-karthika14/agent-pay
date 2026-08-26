"""
Purpose: Pydantic schemas for Claude-initiated authorization requests
(plan.md Phase 2 -- Claude proposes terms, a human Reject/Edit/Approves).

A request row is never itself spending authority -- approving one produces a
real signed Mandate through the existing app.mandates.service code path.
This module is pure data shape; app.authorization.service owns the logic.
"""
from datetime import datetime

from pydantic import BaseModel, Field


class RequestAuthorizationInput(BaseModel):
    """
    Claude's proposed terms for a cart it has already created and populated,
    submitted via request_authorization() (MCP) before any mandate exists.
    user_id/merchant_id are deliberately not accepted here -- both are
    derived from the cart itself, so Claude can never mismatch them.
    """

    cart_id: str
    product_type: str = Field(description='e.g. "wireless earbuds"')
    max_amount_minor: int = Field(gt=0, description="Claude's suggested spending cap, in minor currency units.")
    allowed_categories: list[str]
    allow_addons: bool = False
    delivery_requirement: str = "under_3_days"
    single_use: bool = True
    expires_in_hours: int = Field(default=24, gt=0)
    notes: str | None = Field(default=None, description='e.g. "no unnecessary accessories"')
    reason: str | None = Field(default=None, description="Claude's own justification for this ask, shown to the human.")


class ApproveAuthorizationRequest(BaseModel):
    """
    The (possibly human-edited) terms submitted via POST
    .../{request_id}/approve. Whatever is submitted here -- not what Claude
    originally asked for -- is exactly what gets signed into the resulting
    mandate.
    """

    product_type: str
    max_amount_minor: int = Field(gt=0)
    allowed_categories: list[str]
    allow_addons: bool = False
    delivery_requirement: str = "under_3_days"
    single_use: bool = True
    expires_in_hours: int = Field(default=24, gt=0)
    notes: str | None = None


class AuthorizationRequestResponse(BaseModel):
    """An authorization request's public content, for the popup and for MCP's check_authorization_status()."""

    request_id: str
    cart_id: str
    status: str
    product_type: str
    max_amount_minor: int
    allowed_categories: list[str]
    allow_addons: bool
    delivery_requirement: str
    single_use: bool
    expires_in_hours: int
    notes: str | None
    reason: str | None
    resulting_mandate_id: str | None = Field(
        default=None, description='Business-facing mandate_id (e.g. "M-001"), set once approved.'
    )
    created_at: datetime
    decided_at: datetime | None
