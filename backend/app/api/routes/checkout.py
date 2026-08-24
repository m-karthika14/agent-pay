"""
Purpose: Checkout API route (plan.md Section 18 — Checkout).

Phase 3 scope: only POST /api/checkout/request exists. POST
/api/checkout/{checkout_id}/complete is added in Phase 4/5 once Razorpay
payment execution exists to actually complete -- there's nothing for it to
do yet.
"""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.schemas.checkout import CheckoutRequest, CheckoutResponse
from app.schemas.common import ApiSuccessResponse
from app.services import checkout_service

router = APIRouter(prefix="/api/checkout", tags=["checkout"])


@router.post("/request", response_model=ApiSuccessResponse[CheckoutResponse])
async def request_checkout(
    body: CheckoutRequest, session: AsyncSession = Depends(get_db_session)
) -> ApiSuccessResponse[CheckoutResponse]:
    """Run AgentPay's deterministic hard checks and freeze the cart if they pass."""
    result = await checkout_service.request_checkout(session, uuid.UUID(body.cart_id), body.mandate_id)
    return ApiSuccessResponse(data=result)
