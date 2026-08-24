"""
Purpose: Pydantic schemas for the checkout request API.

Phase 3 scope only: freezing a cart against hard checks. Merchant-proposal
and intent-gate fields (Section 15 steps 9-13) are added to this schema in
Phase 6/7/8 when those components exist -- CheckoutResponse deliberately has
no `proposal`/`intent_decision` fields yet.
"""
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.cart import CartResponse


class CheckoutRequest(BaseModel):
    """Request body for POST /api/checkout/request."""

    cart_id: str
    mandate_id: str = Field(description='Business-facing mandate_id (e.g. "M-001"), not the internal UUID.')


class CheckoutResponse(BaseModel):
    """
    Result of a successful request_checkout() call: the now-FROZEN cart,
    its hash, and when it was frozen.
    """

    cart: CartResponse
    frozen_hash: str
    frozen_at: datetime
