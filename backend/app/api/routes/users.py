"""
Purpose: Demo user identity route (plan.md Section 19 — storefront support).

Thin HTTP layer over app.mandates.service.get_or_create_user -- the same
lookup-or-create-by-email function POST /api/mandates already uses
internally, exposed here so the storefront can resolve a stable user_id
*before* checkout (carts require a real User row from the moment they're
created, well before any mandate exists).
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.mandates.service import get_or_create_user
from app.schemas.common import ApiSuccessResponse
from app.schemas.user import GetOrCreateUserRequest, UserResponse

router = APIRouter(prefix="/api/users", tags=["users"])


@router.post("", response_model=ApiSuccessResponse[UserResponse])
async def get_or_create_user_route(
    body: GetOrCreateUserRequest, session: AsyncSession = Depends(get_db_session)
) -> ApiSuccessResponse[UserResponse]:
    """Resolve (or create, on first sight) a demo user by email."""
    user = await get_or_create_user(session, body.email, body.name)
    return ApiSuccessResponse(
        data=UserResponse(user_id=str(user.id), email=user.email, name=user.name)
    )
