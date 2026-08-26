"""
Purpose: Mandate API routes (plan.md Section 18 — Mandate).

Thin HTTP layer: all real logic lives in app.mandates.service and
app.security.mandate_verifier. This is the buyer-facing entry point that
was missing until now -- a human states their purchase intent/constraints
here, AgentPay signs and persists the resulting mandate, and the returned
mandate_id is what the buyer hands to Claude (via MCP) to authorize a
purchase on their behalf (plan.md Rule 3: intent is signed into the
mandate before any agent acts on it).
"""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_db_session
from app.mandates.service import (
    create_mandate_from_request,
    get_mandate_by_business_id,
    list_mandates_for_user,
    to_mandate_response,
    to_signed_mandate,
)
from app.schemas.common import ApiSuccessResponse, NotFoundError
from app.schemas.mandate import CreateMandateRequest, MandateResponse, MandateVerificationResult
from app.security.mandate_verifier import verify_mandate

router = APIRouter(prefix="/api/mandates", tags=["mandates"])


@router.get("/by-user/{user_id}", response_model=ApiSuccessResponse[list[MandateResponse]])
async def list_mandates_for_user_route(
    user_id: uuid.UUID, session: AsyncSession = Depends(get_db_session)
) -> ApiSuccessResponse[list[MandateResponse]]:
    """List every mandate a user has ever authorized, newest first."""
    result = await list_mandates_for_user(session, user_id)
    return ApiSuccessResponse(data=result)


@router.post("", response_model=ApiSuccessResponse[MandateResponse])
async def create_mandate(
    request: CreateMandateRequest, session: AsyncSession = Depends(get_db_session)
) -> ApiSuccessResponse[MandateResponse]:
    """Sign and persist a new mandate from a buyer's stated intent, returning its mandate_id."""
    result = await create_mandate_from_request(session, request)
    return ApiSuccessResponse(data=result)


@router.get("/{mandate_id}", response_model=ApiSuccessResponse[MandateResponse])
async def get_mandate(
    mandate_id: str, session: AsyncSession = Depends(get_db_session)
) -> ApiSuccessResponse[MandateResponse]:
    """Fetch a mandate's public, decoded content by its business-facing mandate_id (e.g. 'M-001')."""
    row = await get_mandate_by_business_id(session, mandate_id)
    if row is None:
        raise NotFoundError("MANDATE_NOT_FOUND", f"No mandate with id '{mandate_id}'.")
    return ApiSuccessResponse(data=to_mandate_response(row))


@router.post("/{mandate_id}/verify", response_model=ApiSuccessResponse[MandateVerificationResult])
async def verify_mandate_route(
    mandate_id: str, session: AsyncSession = Depends(get_db_session)
) -> ApiSuccessResponse[MandateVerificationResult]:
    """
    Verify a mandate's signature and lifecycle state (signature, expiry,
    single-use/consumed status) -- without a specific cart to check amount/
    category/currency against, matching app.security.mandate_verifier
    .verify_mandate()'s optional-context design.
    """
    row = await get_mandate_by_business_id(session, mandate_id)
    if row is None:
        raise NotFoundError("MANDATE_NOT_FOUND", f"No mandate with id '{mandate_id}'.")

    signed_mandate = to_signed_mandate(row)
    public_key_b64 = get_settings().ed25519_public_key_b64
    result = verify_mandate(signed_mandate, public_key_b64, current_status=row.status)
    return ApiSuccessResponse(data=result)
