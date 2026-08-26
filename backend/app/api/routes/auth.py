"""
Purpose: Storefront login route (plan.md Section 19 -- buyer identity).
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.service import login_or_claim
from app.db.session import get_db_session
from app.schemas.common import ApiSuccessResponse
from app.schemas.user import LoginRequest, UserResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=ApiSuccessResponse[UserResponse])
async def login(
    body: LoginRequest, session: AsyncSession = Depends(get_db_session)
) -> ApiSuccessResponse[UserResponse]:
    """
    Log in by email + password -- or sign up / claim a password-less
    account (see app.auth.service.login_or_claim) if this is the first
    time this email has ever logged in.
    """
    user = await login_or_claim(session, body.email, body.password, body.name)
    return ApiSuccessResponse(data=UserResponse(user_id=str(user.id), email=user.email, name=user.name))
