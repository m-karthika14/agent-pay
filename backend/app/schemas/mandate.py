"""
Purpose: Pydantic schemas for the AgentPay signed mandate.

Responsibilities:
- Define the exact fields a mandate carries (plan.md Section 9.1).
- Define the wrapper around a canonicalized-and-signed mandate payload.
- Define the mandate lifecycle status used by persistence and verification.

This module contains no signing, verification, or database logic — it is pure
data shape. Canonicalization lives in app.security.canonical, signing in
app.security.signing, and full verification in app.security.mandate_verifier.

IMPORTANT: `max_amount` is stored in the smallest currency unit (minor units,
e.g. paise for INR), consistent with how money is stored everywhere else in
AgentPay (plan.md Section 8.3). A mandate authorizing "up to ₹3,000" therefore
sets `max_amount=300000`.
"""
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class MandateStatus(StrEnum):
    """Lifecycle state of a persisted mandate row."""

    ACTIVE = "ACTIVE"
    CONSUMED = "CONSUMED"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"


class MandateIntent(BaseModel):
    """
    The user's free-form purchase intent, captured at authorization time.

    This is signed as part of the mandate so the merchant revenue agent
    cannot rewrite what the user actually asked for (plan.md Rule 3).
    """

    product_type: str = Field(description='e.g. "wireless earbuds"')
    notes: str | None = Field(
        default=None, description='e.g. "no unnecessary accessories"'
    )


class MandatePayload(BaseModel):
    """
    The canonical, unsigned content of an AgentPay mandate.

    This is exactly the set of fields defined in plan.md Section 9.1. Nothing
    else belongs here — in particular, `cart_hash` must NEVER be added to this
    model (plan.md Rule 4): the cart does not exist yet at authorization time,
    and it is hashed separately when `request_checkout` freezes it.
    """

    mandate_id: str
    merchant_id: str
    currency: str = Field(description='ISO 4217 currency code, e.g. "INR"')
    max_amount: int = Field(
        gt=0, description="Authorized spending cap, in minor currency units"
    )
    allowed_categories: list[str]
    allow_addons: bool
    delivery_requirement: str
    single_use: bool
    expires_at: datetime
    intent: MandateIntent


class SignedMandate(BaseModel):
    """
    A mandate payload plus its Ed25519 signature.

    `signature` is the base64-encoded Ed25519 signature over the canonical
    byte representation of `payload` (see app.security.canonical and
    app.security.signing). This is the artifact persisted to the `mandates`
    table (as `signed_payload` + `signature`) and passed around the system.
    """

    payload: MandatePayload
    signature: str


class MandateVerificationResult(BaseModel):
    """
    Deterministic outcome of verifying a signed mandate.

    Returned by app.security.mandate_verifier.verify_mandate(). `valid=False`
    always carries a `reason_code` from app.policy.reason_codes so callers can
    audit *why* a mandate was rejected without re-deriving it from prose.
    """

    valid: bool
    reason_code: str | None = None
    reason: str | None = None
