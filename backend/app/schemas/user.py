"""
Purpose: Pydantic schemas for the demo user identity/login endpoints.

Email is the natural identity key throughout (plan.md Section 19): POST
/api/users idempotently resolves it to a stable user_id with no password
(still how Claude/MCP identifies a buyer), while POST /api/auth/login adds
a real password check on top of that same User row -- see
app.auth.service.login_or_claim for why a password-less row created via
/api/users can still log in (its password gets claimed on first login).
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


class LoginRequest(BaseModel):
    """Request body for POST /api/auth/login."""

    email: str
    password: str = Field(min_length=1)
    name: str = Field(default="Storefront Buyer", description="Used only if this email has never signed up before.")
