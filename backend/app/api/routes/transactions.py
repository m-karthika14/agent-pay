"""
Purpose: Read-only transaction API routes (plan.md Section 18 — Transactions).
"""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.schemas.common import ApiSuccessResponse
from app.schemas.payment import TransactionResponse, TransactionTraceResponse
from app.services import transaction_service

router = APIRouter(prefix="/api/transactions", tags=["transactions"])


@router.get("/{transaction_id}", response_model=ApiSuccessResponse[TransactionResponse])
async def get_transaction(
    transaction_id: uuid.UUID, session: AsyncSession = Depends(get_db_session)
) -> ApiSuccessResponse[TransactionResponse]:
    """Fetch a single transaction by id."""
    result = await transaction_service.get_transaction(session, transaction_id)
    return ApiSuccessResponse(data=result)


@router.get("/{transaction_id}/trace", response_model=ApiSuccessResponse[TransactionTraceResponse])
async def get_transaction_trace(
    transaction_id: uuid.UUID, session: AsyncSession = Depends(get_db_session)
) -> ApiSuccessResponse[TransactionTraceResponse]:
    """Fetch a transaction's complete ordered audit trace."""
    result = await transaction_service.get_transaction_trace(session, transaction_id)
    return ApiSuccessResponse(data=result)
