"""
Purpose: Merchant Console overview API routes (plan.md Section 18 —
Evaluation/console, Section 19.2).

Thin HTTP layer: all real logic lives in app.services.console_service and
app.services.audit_service.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.schemas.audit import AuditEventRecord
from app.schemas.common import ApiSuccessResponse
from app.schemas.console import ConsoleMetricsResponse, ConsoleSummaryResponse
from app.services import audit_service, console_service

router = APIRouter(prefix="/api/console", tags=["console"])


@router.get("/summary", response_model=ApiSuccessResponse[ConsoleSummaryResponse])
async def get_console_summary(
    session: AsyncSession = Depends(get_db_session),
) -> ApiSuccessResponse[ConsoleSummaryResponse]:
    """Fetch aggregate transaction/mandate/audit counts plus recent activity."""
    result = await console_service.get_summary(session)
    return ApiSuccessResponse(data=result)


@router.get("/events", response_model=ApiSuccessResponse[list[AuditEventRecord]])
async def get_console_events(
    limit: int = Query(default=25, ge=1, le=200),
    session: AsyncSession = Depends(get_db_session),
) -> ApiSuccessResponse[list[AuditEventRecord]]:
    """Fetch the most recent audit events system-wide (a live decision feed), newest first."""
    events = await audit_service.get_recent_events(session, limit)
    return ApiSuccessResponse(data=events)


@router.get("/metrics", response_model=ApiSuccessResponse[ConsoleMetricsResponse])
async def get_console_metrics() -> ApiSuccessResponse[ConsoleMetricsResponse]:
    """Fetch the Phase 10 evaluation report (Cap-only vs Intent-aware ceiling drift, etc.), if run."""
    result = console_service.get_metrics()
    return ApiSuccessResponse(data=result)
