"""
Purpose: Audit log API routes (plan.md Section 18 — Audit, Section 24
"Audit viewer").

Thin HTTP layer: all real logic lives in app.services.audit_service.
"""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.schemas.audit import AuditEventRecord, ChainVerificationResult
from app.schemas.common import ApiSuccessResponse
from app.services import audit_service

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("/by-mandate/{mandate_id}", response_model=ApiSuccessResponse[list[AuditEventRecord]])
async def get_mandate_audit_events(
    mandate_id: str, session: AsyncSession = Depends(get_db_session)
) -> ApiSuccessResponse[list[AuditEventRecord]]:
    """
    Fetch a mandate's own audit events, oldest first -- works from the
    moment the mandate is created, before any cart is frozen or payment
    attempted under it. Polled by the live "AI Activity" panel.
    """
    events = await audit_service.get_events_for_mandate(session, mandate_id)
    return ApiSuccessResponse(data=events)


@router.get("/{transaction_id}", response_model=ApiSuccessResponse[list[AuditEventRecord]])
async def get_transaction_audit_events(
    transaction_id: uuid.UUID, session: AsyncSession = Depends(get_db_session)
) -> ApiSuccessResponse[list[AuditEventRecord]]:
    """Fetch a transaction's own audit events, oldest first, with full hash-chain fields."""
    events = await audit_service.get_events_for_transaction(session, transaction_id)
    return ApiSuccessResponse(data=events)


@router.get("/{transaction_id}/verify", response_model=ApiSuccessResponse[ChainVerificationResult])
async def verify_audit_chain(
    transaction_id: uuid.UUID, session: AsyncSession = Depends(get_db_session)
) -> ApiSuccessResponse[ChainVerificationResult]:
    """
    Verify AgentPay's entire hash-chained audit log.

    Note: `transaction_id` identifies which transaction's audit page
    triggered this check, but the chain itself is global (plan.md Section
    23.2 -- every event links to whichever event preceded it system-wide),
    so verification necessarily covers the whole ledger, not a filtered
    slice scoped to one transaction. This mirrors scripts/verify_audit_chain.py.
    """
    result = await audit_service.verify_full_chain(session, transaction_id)
    return ApiSuccessResponse(data=result)
