"""
Purpose: Authorization-request API routes (plan.md Phase 2).

Thin HTTP layer: all real logic lives in app.authorization.service. This is
what the storefront's global "Claude wants to buy" popup polls and acts
against -- request_authorization()/check_authorization_status() (MCP, used
by Claude) call the exact same service functions directly, not this router.
"""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.authorization.service import (
    approve_authorization_request,
    get_authorization_request,
    list_pending_for_user,
    reject_authorization_request,
)
from app.db.session import get_db_session
from app.schemas.authorization import ApproveAuthorizationRequest, AuthorizationRequestResponse
from app.schemas.common import ApiSuccessResponse

router = APIRouter(prefix="/api/authorization-requests", tags=["authorization-requests"])


@router.get("/by-user/{user_id}", response_model=ApiSuccessResponse[list[AuthorizationRequestResponse]])
async def list_pending_for_user_route(
    user_id: uuid.UUID, session: AsyncSession = Depends(get_db_session)
) -> ApiSuccessResponse[list[AuthorizationRequestResponse]]:
    """List every PENDING authorization request across a user's carts. Polled by the global popup."""
    result = await list_pending_for_user(session, user_id)
    return ApiSuccessResponse(data=result)


@router.get("/{request_id}", response_model=ApiSuccessResponse[AuthorizationRequestResponse])
async def get_authorization_request_route(
    request_id: uuid.UUID, session: AsyncSession = Depends(get_db_session)
) -> ApiSuccessResponse[AuthorizationRequestResponse]:
    """Fetch one authorization request by id."""
    result = await get_authorization_request(session, request_id)
    return ApiSuccessResponse(data=result)


@router.post("/{request_id}/approve", response_model=ApiSuccessResponse[AuthorizationRequestResponse])
async def approve_authorization_request_route(
    request_id: uuid.UUID, body: ApproveAuthorizationRequest, session: AsyncSession = Depends(get_db_session)
) -> ApiSuccessResponse[AuthorizationRequestResponse]:
    """Approve a PENDING request, signing a real mandate from `body` -- the human's (possibly edited) terms."""
    result = await approve_authorization_request(session, request_id, body)
    return ApiSuccessResponse(data=result)


@router.post("/{request_id}/reject", response_model=ApiSuccessResponse[AuthorizationRequestResponse])
async def reject_authorization_request_route(
    request_id: uuid.UUID, session: AsyncSession = Depends(get_db_session)
) -> ApiSuccessResponse[AuthorizationRequestResponse]:
    """Reject a PENDING request. No mandate is created."""
    result = await reject_authorization_request(session, request_id)
    return ApiSuccessResponse(data=result)
