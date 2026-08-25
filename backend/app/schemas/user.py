"""
Purpose: Pydantic schemas for the demo user identity endpoint.

The storefront has no real authentication (plan.md Section 19 is explicit
that the buyer-facing UI is a demo). Email is the lightweight identity key:
POST /api/users resolves it to a stable user_id, idempotently creating the
row on first sight, so the storefront can create carts (which require a
real User row) before any mandate exists.
"""
from pydantic import BaseModel, Field


class GetOrCreateUserRequest(BaseModel):
    """Request body for POST /api/users."""

    email: str
    name: str = Field(default="Storefront Buyer")


class UserResponse(BaseModel):
    """A demo user's identity."""

    user_id: str
    email: str
    name: str
