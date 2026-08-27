"""
Purpose: Demo user identity route (plan.md Section 19 — storefront support)
and each user's own AI Shopping Budget (plan.md Phase 4).

Thin HTTP layer over app.mandates.service.get_or_create_user -- the same
lookup-or-create-by-email function POST /api/mandates already uses
internally, exposed here so the storefront can resolve a stable user_id
*before* checkout (carts require a real User row from the moment they're
created, well before any mandate exists).
"""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.budgets.service import get_active_budget, set_budget
from app.db.session import get_db_session
from app.mandates.service import get_or_create_user
from app.schemas.budget import BudgetResponse, SetBudgetRequest
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


@router.get("/{user_id}/budget", response_model=ApiSuccessResponse[BudgetResponse])
async def get_budget_route(
    user_id: uuid.UUID, session: AsyncSession = Depends(get_db_session)
) -> ApiSuccessResponse[BudgetResponse]:
    """Fetch this user's current AI Shopping Budget (all-None/is_active=False if never set or expired)."""
    budget = await get_active_budget(session, user_id)
    return ApiSuccessResponse(data=budget)


@router.put("/{user_id}/budget", response_model=ApiSuccessResponse[BudgetResponse])
async def set_budget_route(
    user_id: uuid.UUID, body: SetBudgetRequest, session: AsyncSession = Depends(get_db_session)
) -> ApiSuccessResponse[BudgetResponse]:
    """Set (replacing any prior) AI Shopping Budget for this user -- only a human, via this route, can ever raise Claude's ceiling."""
    budget = await set_budget(session, user_id, body)
    await session.commit()
    return ApiSuccessResponse(data=budget)
