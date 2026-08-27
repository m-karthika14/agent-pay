"""
Purpose: Pydantic schemas for a user's own "AI Shopping Budget" -- an
independent spending ceiling the user sets themselves, before Claude ever
asks for anything (plan.md Phase 4).

This is deliberately not a Mandate: a Mandate is created once Claude has
already found something to buy and a human approves it. The budget exists
before that, as the number app.authorization.service checks a Claude-
initiated authorization_request against.
"""
from datetime import datetime

from pydantic import BaseModel, Field


class SetBudgetRequest(BaseModel):
    """Request body for PUT /api/users/{user_id}/budget."""

    max_amount_minor: int = Field(gt=0, description="Absolute ceiling, in minor currency units, on what Claude may ever request.")
    allow_addons: bool = Field(default=True, description="Whether the Merchant Agent may propose add-ons at all.")
    expires_in_hours: int = Field(default=24, gt=0)


class BudgetResponse(BaseModel):
    """A user's current AI Shopping Budget, or all-None fields if they haven't set one (or it has expired)."""

    max_amount_minor: int | None
    allow_addons: bool | None
    currency: str = "INR"
    expires_at: datetime | None
    is_active: bool
