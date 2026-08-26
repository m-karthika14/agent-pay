"""
Purpose: Order API routes (plan.md Section 18/19) -- buyer order history
plus a payment-status sync fallback for when Razorpay's webhook can't
reach the backend (e.g. local dev with no public URL).
"""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.payments.reconciliation import sync_order
from app.schemas.common import ApiSuccessResponse
from app.schemas.payment import OrderHistoryEntry, OrderSummary
from app.services import transaction_service

router = APIRouter(prefix="/api/orders", tags=["orders"])


@router.get("/by-user/{user_id}", response_model=ApiSuccessResponse[list[OrderHistoryEntry]])
async def list_orders_for_user(
    user_id: uuid.UUID, session: AsyncSession = Depends(get_db_session)
) -> ApiSuccessResponse[list[OrderHistoryEntry]]:
    """List every order a user has ever placed, newest first."""
    result = await transaction_service.list_orders_for_user(session, user_id)
    return ApiSuccessResponse(data=result)


@router.post("/{order_id}/sync", response_model=ApiSuccessResponse[OrderSummary])
async def sync_order_route(
    order_id: uuid.UUID, session: AsyncSession = Depends(get_db_session)
) -> ApiSuccessResponse[OrderSummary]:
    """
    Re-check an order's payment status directly against Razorpay and
    correct AgentPay's stored state if a webhook delivery was missed.
    """
    result = await sync_order(session, order_id)
    return ApiSuccessResponse(data=result)
