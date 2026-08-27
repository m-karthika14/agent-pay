"""
Purpose: A user's own "AI Shopping Budget" -- an independent spending
ceiling they set themselves, before Claude ever creates an
authorization_request (plan.md Phase 4).

Stored directly on the User row (ai_budget_* columns) rather than a new
table: a user has at most one active budget at a time, and it's read on
every create_authorization_request()/approve_authorization_request() call,
so a single row lookup (already happening for other fields) is simplest.

This module owns the two things Claude cannot do:
- Set its own ceiling (only a human, via set_budget(), can).
- See the budget as anything other than a hard number to stay under --
  app.authorization.service is what actually enforces it.
"""
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.user import User
from app.schemas.budget import BudgetResponse, SetBudgetRequest
from app.schemas.common import NotFoundError


def _to_response(user: User) -> BudgetResponse:
    is_active = (
        user.ai_budget_max_amount_minor is not None
        and user.ai_budget_expires_at is not None
        and user.ai_budget_expires_at > datetime.now(UTC)
    )
    return BudgetResponse(
        max_amount_minor=user.ai_budget_max_amount_minor if is_active else None,
        allow_addons=user.ai_budget_allow_addons if is_active else None,
        expires_at=user.ai_budget_expires_at if is_active else None,
        is_active=is_active,
    )


async def _get_user_or_raise(session: AsyncSession, user_id: uuid.UUID) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise NotFoundError("USER_NOT_FOUND", f"No user with id '{user_id}'.")
    return user


async def get_active_budget(session: AsyncSession, user_id: uuid.UUID) -> BudgetResponse:
    """
    Fetch a user's AI Shopping Budget. Returns an all-None, `is_active=False`
    response (not an error) if they've never set one, or if it has expired --
    both are normal states, not failures.
    """
    user = await _get_user_or_raise(session, user_id)
    return _to_response(user)


async def set_budget(session: AsyncSession, user_id: uuid.UUID, body: SetBudgetRequest) -> BudgetResponse:
    """
    Set (or replace) a user's AI Shopping Budget. Always fully overwrites
    any prior budget -- there is exactly one active budget per user, never a
    history of them, since only the current ceiling matters to enforcement.
    """
    user = await _get_user_or_raise(session, user_id)
    user.ai_budget_max_amount_minor = body.max_amount_minor
    user.ai_budget_allow_addons = body.allow_addons
    user.ai_budget_expires_at = datetime.now(UTC) + timedelta(hours=body.expires_in_hours)
    await session.flush()
    return _to_response(user)
