"""
Purpose: Pydantic schemas for the checkout request API.

Phase 3 laid the groundwork (freezing a cart against hard checks); Phase 8
adds the merchant-proposal/intent-gate outcome (plan.md Section 15 steps
9-13) to CheckoutResponse.
"""
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.cart import CartResponse
from app.schemas.proposal import ProposalStatus


class CheckoutRequest(BaseModel):
    """
    Request body for POST /api/checkout/request.

    mandate_id is optional (plan.md Phase 2.1): omit it to let AgentPay
    resolve the cart's own already-approved authorization request (or its
    already-frozen mandate, on a retry) instead -- see
    app.services.checkout_service.request_checkout()'s resolution logic.
    """

    cart_id: str
    mandate_id: str | None = Field(
        default=None, description='Business-facing mandate_id (e.g. "M-001"), not the internal UUID. Omit to let AgentPay resolve it from the cart.'
    )


class CompleteCheckoutRequest(BaseModel):
    """Request body for POST /api/checkout/{cart_id}/complete (cart_id comes from the URL path)."""

    mandate_id: str = Field(description='Business-facing mandate_id (e.g. "M-001"), not the internal UUID.')


class ProposalOutcome(BaseModel):
    """
    What happened, if anything, to a Merchant Revenue Agent proposal during
    one request_checkout() call (plan.md Section 15 steps 9-13).

    status mirrors app.schemas.proposal.ProposalStatus:
    - NO_PROPOSAL / ORIGINAL_CART_RETAINED: the merchant agent never got a
      proposal through its own deterministic hard-check pathway (Phase 6,
      app.services.merchant_service.evaluate_proposal) -- the Intent Gate
      was never invoked.
    - PROPOSAL_ALLOWED / PROPOSAL_REJECTED / PROPOSAL_ESCALATED: reflect the
      Intent Gate's verdict (Phase 7) on a proposal that DID pass those hard
      checks. Only PROPOSAL_ALLOWED means the proposal was actually applied
      to the cart; the other two mean the original cart was retained
      unmodified (plan.md Section 6.2/6.3: rejecting or escalating a
      proposal is non-terminal for the underlying transaction).
    """

    status: ProposalStatus
    product_id: str | None = None
    quantity: int | None = None
    reason: str | None = None
    reason_code: str | None = None
    intent_confidence: float | None = None


class CheckoutResponse(BaseModel):
    """
    Result of a successful request_checkout() call: the now-FROZEN cart
    (possibly modified by an Intent-Gate-approved merchant proposal), its
    hash, when it was frozen, and what happened with any merchant proposal.
    """

    cart: CartResponse
    frozen_hash: str
    frozen_at: datetime
    proposal: ProposalOutcome | None = None
