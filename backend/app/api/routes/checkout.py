"""
Purpose: Checkout API routes (plan.md Section 18 — Checkout).

POST /api/checkout/request  (Phase 3): run hard checks, freeze the cart.
POST /api/checkout/{cart_id}/complete  (Phase 4): create the Razorpay order
for an already-frozen cart. "Complete" here means "create the checkout
session a human completes via Razorpay Standard Checkout" -- plan.md
Section 22 is explicit that a human/test operator completes the actual
Test Mode Checkout UI, not this backend and not Claude directly. The
authoritative payment-completion signal is the Razorpay webhook
(POST /api/webhooks/razorpay), handled separately.
"""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.payments.checkout import create_checkout_session
from app.schemas.checkout import CheckoutRequest, CheckoutResponse, CompleteCheckoutRequest
from app.schemas.common import ApiSuccessResponse
from app.schemas.payment import CheckoutSessionResponse
from app.services import checkout_service

router = APIRouter(prefix="/api/checkout", tags=["checkout"])


@router.post("/request", response_model=ApiSuccessResponse[CheckoutResponse])
async def request_checkout(
    body: CheckoutRequest, session: AsyncSession = Depends(get_db_session)
) -> ApiSuccessResponse[CheckoutResponse]:
    """Run AgentPay's deterministic hard checks and freeze the cart if they pass."""
    result = await checkout_service.request_checkout(session, uuid.UUID(body.cart_id), body.mandate_id)
    return ApiSuccessResponse(data=result)


@router.post("/{cart_id}/complete", response_model=ApiSuccessResponse[CheckoutSessionResponse])
async def complete_checkout(
    cart_id: uuid.UUID, body: CompleteCheckoutRequest, session: AsyncSession = Depends(get_db_session)
) -> ApiSuccessResponse[CheckoutSessionResponse]:
    """Create (or idempotently re-return) a Razorpay order for a frozen cart."""
    result = await create_checkout_session(session, cart_id, body.mandate_id)
    return ApiSuccessResponse(data=result)
