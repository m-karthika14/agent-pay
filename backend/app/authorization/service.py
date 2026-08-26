"""
Purpose: Create, list, and decide Claude-initiated authorization requests
(plan.md Phase 2).

Responsibilities:
- Let a buyer agent (Claude, via MCP) propose spending terms for a cart it
  has already created -- before any mandate exists.
- Let a human Reject or Approve (optionally with edited terms) a pending
  request from the storefront's global popup.

Approving a request never signs a mandate itself here -- it calls the
existing app.mandates.service.create_mandate_from_request(), the exact same
function /authorize-agent already uses. That is the entire trust boundary
this module exists to enforce: Claude can create and poll a request, but
only a human's approval action (routed through this module) can turn it
into real spending authority, and only by handing the (possibly edited)
terms to code that already existed before this feature.
"""
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import append_event
from app.carts.service import get_cart
from app.db.models.authorization_request import AuthorizationRequest, AuthorizationRequestStatus
from app.db.models.cart import Cart
from app.db.models.mandate import Mandate
from app.db.models.user import User
from app.mandates.service import create_mandate_from_request, get_mandate_by_business_id
from app.schemas.audit import AuditEventInput
from app.schemas.authorization import (
    ApproveAuthorizationRequest,
    AuthorizationRequestResponse,
    RequestAuthorizationInput,
)
from app.schemas.common import NotFoundError, ValidationError
from app.schemas.mandate import CreateMandateRequest


def _to_response(row: AuthorizationRequest) -> AuthorizationRequestResponse:
    return AuthorizationRequestResponse(
        request_id=str(row.id),
        cart_id=str(row.cart_id),
        status=row.status.value,
        product_type=row.product_type,
        max_amount_minor=row.max_amount_minor,
        allowed_categories=list(row.allowed_categories),
        allow_addons=row.allow_addons,
        delivery_requirement=row.delivery_requirement,
        single_use=row.single_use,
        expires_in_hours=row.expires_in_hours,
        notes=row.notes,
        reason=row.reason,
        resulting_mandate_id=None,
        created_at=row.created_at,
        decided_at=row.decided_at,
    )


async def _to_response_with_mandate(session: AsyncSession, row: AuthorizationRequest) -> AuthorizationRequestResponse:
    response = _to_response(row)
    if row.resulting_mandate_id is not None:
        mandate_row = await session.get(Mandate, row.resulting_mandate_id)
        response.resulting_mandate_id = mandate_row.mandate_id if mandate_row else None
    return response


async def _get_request_or_raise(session: AsyncSession, request_id: uuid.UUID) -> AuthorizationRequest:
    row = await session.get(AuthorizationRequest, request_id)
    if row is None:
        raise NotFoundError("AUTHORIZATION_REQUEST_NOT_FOUND", f"No authorization request with id '{request_id}'.")
    return row


async def create_authorization_request(
    session: AsyncSession, input_data: RequestAuthorizationInput
) -> AuthorizationRequestResponse:
    """
    Record Claude's proposed spending terms for a cart it has already
    created and populated (plan.md Phase 2 -- request_authorization()).

    Args:
        session: Active AsyncSession.
        input_data: Claude's proposed terms (cart_id + suggested mandate
            fields + an optional natural-language reason).

    Returns:
        The newly created PENDING request.

    Raises:
        NotFoundError: If the cart does not exist.
        ValidationError: If the cart is not OPEN, or a PENDING request
            already exists for it.
    """
    cart_id = uuid.UUID(input_data.cart_id)
    cart = await get_cart(session, cart_id)
    if cart.status != "OPEN":
        raise ValidationError(
            "CART_NOT_OPEN", f"Cart '{cart_id}' is '{cart.status}'; only an OPEN cart can request authorization."
        )

    existing = await session.execute(
        select(AuthorizationRequest).where(
            AuthorizationRequest.cart_id == cart_id,
            AuthorizationRequest.status == AuthorizationRequestStatus.PENDING,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise ValidationError(
            "AUTHORIZATION_ALREADY_PENDING",
            f"Cart '{cart_id}' already has a pending authorization request; check its status before asking again.",
        )

    row = AuthorizationRequest(
        cart_id=cart_id,
        status=AuthorizationRequestStatus.PENDING,
        max_amount_minor=input_data.max_amount_minor,
        allowed_categories=input_data.allowed_categories,
        allow_addons=input_data.allow_addons,
        delivery_requirement=input_data.delivery_requirement,
        single_use=input_data.single_use,
        expires_in_hours=input_data.expires_in_hours,
        product_type=input_data.product_type,
        notes=input_data.notes,
        reason=input_data.reason,
    )
    session.add(row)
    await session.flush()

    await append_event(
        session,
        AuditEventInput(
            event_type="AUTHORIZATION_REQUESTED",
            actor_type="BUYER_AGENT",
            payload={
                "request_id": str(row.id),
                "cart_id": str(cart_id),
                "max_amount_minor": input_data.max_amount_minor,
                "allowed_categories": input_data.allowed_categories,
                "reason": input_data.reason,
            },
            user_id=str(cart.user_id),
        ),
    )
    return _to_response(row)


async def get_authorization_request(session: AsyncSession, request_id: uuid.UUID) -> AuthorizationRequestResponse:
    """Fetch one authorization request by id -- used by check_authorization_status() and the popup's detail view."""
    row = await _get_request_or_raise(session, request_id)
    return await _to_response_with_mandate(session, row)


async def list_pending_for_user(session: AsyncSession, user_id: uuid.UUID) -> list[AuthorizationRequestResponse]:
    """
    List every PENDING authorization request across a user's carts, oldest
    first -- what the storefront's global popup polls.

    Joins through Cart rather than storing user_id directly on
    AuthorizationRequest, since a cart's owner never changes after creation.
    """
    result = await session.execute(
        select(AuthorizationRequest)
        .join(Cart, Cart.id == AuthorizationRequest.cart_id)
        .where(Cart.user_id == user_id, AuthorizationRequest.status == AuthorizationRequestStatus.PENDING)
        .order_by(AuthorizationRequest.created_at)
    )
    return [_to_response(row) for row in result.scalars().all()]


async def approve_authorization_request(
    session: AsyncSession, request_id: uuid.UUID, terms: ApproveAuthorizationRequest
) -> AuthorizationRequestResponse:
    """
    Approve a PENDING request, signing a real mandate from `terms` -- the
    (possibly human-edited) values submitted here, not necessarily what
    Claude originally asked for.

    Args:
        session: Active AsyncSession.
        request_id: The request to approve.
        terms: The terms to sign into the mandate. If the human used the
            popup's Edit form, this reflects their edits; if they approved
            as-is, it's an unmodified copy of the request's own suggested
            terms.

    Returns:
        The request, now APPROVED, with resulting_mandate_id set.

    Raises:
        NotFoundError: If the request or its cart's user does not exist.
        ValidationError: If the request is not PENDING.
    """
    row = await _get_request_or_raise(session, request_id)
    if row.status != AuthorizationRequestStatus.PENDING:
        raise ValidationError(
            "AUTHORIZATION_NOT_PENDING", f"Authorization request '{request_id}' is already '{row.status.value}'."
        )

    cart = await session.get(Cart, row.cart_id)
    if cart is None:
        raise NotFoundError("CART_NOT_FOUND", f"No cart with id '{row.cart_id}'.")
    user = await session.get(User, cart.user_id)
    if user is None:
        raise NotFoundError("USER_NOT_FOUND", f"No user with id '{cart.user_id}'.")

    mandate = await create_mandate_from_request(
        session,
        CreateMandateRequest(
            user_email=user.email,
            user_name=user.name,
            merchant_id=str(cart.merchant_id),
            currency=cart.currency,
            max_amount_minor=terms.max_amount_minor,
            allowed_categories=terms.allowed_categories,
            allow_addons=terms.allow_addons,
            delivery_requirement=terms.delivery_requirement,
            single_use=terms.single_use,
            expires_in_hours=terms.expires_in_hours,
            product_type=terms.product_type,
            notes=terms.notes,
        ),
    )
    mandate_row = await get_mandate_by_business_id(session, mandate.mandate_id)

    row.status = AuthorizationRequestStatus.APPROVED
    row.resulting_mandate_id = mandate_row.id if mandate_row else None
    row.decided_at = datetime.now(UTC)
    await session.flush()

    await append_event(
        session,
        AuditEventInput(
            event_type="AUTHORIZATION_APPROVED",
            actor_type="USER",
            payload={"request_id": str(row.id), "cart_id": str(row.cart_id), "mandate_id": mandate.mandate_id},
            mandate_id=str(mandate_row.id) if mandate_row else None,
            user_id=str(cart.user_id),
        ),
    )
    return await _to_response_with_mandate(session, row)


async def reject_authorization_request(session: AsyncSession, request_id: uuid.UUID) -> AuthorizationRequestResponse:
    """
    Reject a PENDING request. No mandate is created.

    Raises:
        NotFoundError: If the request does not exist.
        ValidationError: If the request is not PENDING.
    """
    row = await _get_request_or_raise(session, request_id)
    if row.status != AuthorizationRequestStatus.PENDING:
        raise ValidationError(
            "AUTHORIZATION_NOT_PENDING", f"Authorization request '{request_id}' is already '{row.status.value}'."
        )

    cart = await session.get(Cart, row.cart_id)

    row.status = AuthorizationRequestStatus.REJECTED
    row.decided_at = datetime.now(UTC)
    await session.flush()

    await append_event(
        session,
        AuditEventInput(
            event_type="AUTHORIZATION_REJECTED",
            actor_type="USER",
            payload={"request_id": str(row.id), "cart_id": str(row.cart_id)},
            user_id=str(cart.user_id) if cart else None,
        ),
    )
    return _to_response(row)
