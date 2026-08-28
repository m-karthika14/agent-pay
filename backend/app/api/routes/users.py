"""
Purpose: Demo user identity route (plan.md Section 19 — storefront support),
each user's own AI Shopping Budget (plan.md Phase 4), and each user's own
Automatic Payments authorization (plan.md Phase 5) -- deliberately separate
concepts, see app.schemas.payment_authorization's module docstring.

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
from app.payments import authorization_service
from app.schemas.budget import BudgetResponse, SetBudgetRequest
from app.schemas.common import ApiSuccessResponse
from app.schemas.payment_authorization import (
    ConfirmPaymentAuthorizationRequest,
    PaymentAuthorizationResponse,
    SetupPaymentAuthorizationRequest,
    SetupPaymentAuthorizationResponse,
)
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


@router.get("/{user_id}/payment-authorization", response_model=ApiSuccessResponse[PaymentAuthorizationResponse])
async def get_payment_authorization_route(
    user_id: uuid.UUID, session: AsyncSession = Depends(get_db_session)
) -> ApiSuccessResponse[PaymentAuthorizationResponse]:
    """Fetch this user's current Automatic Payments authorization (is_active=False if never set, revoked, or expired)."""
    auth = await authorization_service.get_active_payment_authorization(session, user_id)
    return ApiSuccessResponse(data=auth)


@router.post(
    "/{user_id}/payment-authorization", response_model=ApiSuccessResponse[SetupPaymentAuthorizationResponse]
)
async def setup_payment_authorization_route(
    user_id: uuid.UUID, body: SetupPaymentAuthorizationRequest, session: AsyncSession = Depends(get_db_session)
) -> ApiSuccessResponse[SetupPaymentAuthorizationResponse]:
    """Start the ONE interactive Razorpay Checkout step that registers a reusable payment token."""
    setup = await authorization_service.create_payment_authorization_setup(session, user_id, body)
    await session.commit()
    return ApiSuccessResponse(data=setup)


@router.post(
    "/{user_id}/payment-authorization/confirm", response_model=ApiSuccessResponse[PaymentAuthorizationResponse]
)
async def confirm_payment_authorization_route(
    user_id: uuid.UUID, body: ConfirmPaymentAuthorizationRequest, session: AsyncSession = Depends(get_db_session)
) -> ApiSuccessResponse[PaymentAuthorizationResponse]:
    """Verify the interactive registration payment with Razorpay directly and, only if it genuinely succeeded, activate Automatic Payments."""
    auth = await authorization_service.confirm_payment_authorization(session, user_id, body)
    await session.commit()
    return ApiSuccessResponse(data=auth)


@router.delete("/{user_id}/payment-authorization", response_model=ApiSuccessResponse[PaymentAuthorizationResponse])
async def revoke_payment_authorization_route(
    user_id: uuid.UUID, session: AsyncSession = Depends(get_db_session)
) -> ApiSuccessResponse[PaymentAuthorizationResponse]:
    """Revoke this user's Automatic Payments authorization. AgentPay stops attempting automatic payment immediately."""
    auth = await authorization_service.revoke_payment_authorization(session, user_id)
    await session.commit()
    return ApiSuccessResponse(data=auth)
