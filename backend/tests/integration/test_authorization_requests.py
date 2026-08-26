"""
Purpose: Integration tests for the Claude-initiated authorization-request
flow (plan.md Phase 2) -- request_authorization()/check_authorization_status()
(MCP) and the human's Reject/Edit/Approve path they feed into.

The single most important property under test: approving a request signs a
real mandate through app.mandates.service.create_mandate_from_request --
never a shortcut -- and when the human edits Claude's suggested terms, it is
the EDITED terms that get signed and enforced, not what Claude asked for.

Every test uses its own isolated, throwaway merchant/product/user, matching
tests/integration/test_multi_merchant.py's established convention.
"""
import uuid

from app.authorization.service import (
    approve_authorization_request,
    create_authorization_request,
    get_authorization_request,
    reject_authorization_request,
)
from app.carts.service import add_cart_item, create_cart
from app.core.config import get_settings
from app.db.models.inventory import Inventory
from app.db.models.merchant import Merchant
from app.db.models.product import Product
from app.db.models.user import User
from app.db.session import get_session_factory
from app.mandates.service import get_mandate_by_business_id, to_signed_mandate
from app.schemas.authorization import ApproveAuthorizationRequest, RequestAuthorizationInput
from app.schemas.common import AgentPayError
from app.security.mandate_verifier import verify_mandate
from app.services.audit_service import get_events_for_user
from app.services.checkout_service import request_checkout


async def _create_merchant_with_product(*, category: str = "audio", price_minor: int = 200_000) -> tuple[Merchant, Product, User]:
    factory = get_session_factory()
    unique = uuid.uuid4().hex[:8]
    async with factory() as session:
        merchant = Merchant(slug=f"auth-test-{unique}", name=f"Auth Test Merchant {unique}", currency="INR")
        user = User(email=f"auth-{unique}@agentpay.test", name="Authorization Test Buyer")
        session.add_all([merchant, user])
        await session.flush()

        product = Product(
            merchant_id=merchant.id,
            sku=f"AUTH-{unique}",
            name="Wireless Earbuds",
            description="Test product for authorization-request tests.",
            price_minor=price_minor,
            currency="INR",
            category=category,
            is_active=True,
        )
        session.add(product)
        await session.flush()
        session.add(Inventory(product_id=product.id, quantity=10, reserved_quantity=0))
        await session.commit()
        return merchant, product, user


async def _create_cart_with_item(merchant: Merchant, product: Product, user: User) -> uuid.UUID:
    factory = get_session_factory()
    async with factory() as session:
        cart = await create_cart(session, user.id, merchant.id, "INR")
        await add_cart_item(session, uuid.UUID(cart.cart_id), product.id, 1)
        await session.commit()
        return uuid.UUID(cart.cart_id)


def _suggested_terms(cart_id: uuid.UUID, product: Product, *, max_amount_minor: int) -> RequestAuthorizationInput:
    return RequestAuthorizationInput(
        cart_id=str(cart_id),
        product_type=product.name,
        max_amount_minor=max_amount_minor,
        allowed_categories=[product.category],
        allow_addons=False,
        reason="Matches the buyer's request.",
    )


async def test_request_authorization_creates_pending_request_and_audit_event() -> None:
    merchant, product, user = await _create_merchant_with_product()
    cart_id = await _create_cart_with_item(merchant, product, user)

    factory = get_session_factory()
    async with factory() as session:
        terms = _suggested_terms(cart_id, product, max_amount_minor=300_000)
        request = await create_authorization_request(session, terms)
        await session.commit()

        fetched = await get_authorization_request(session, uuid.UUID(request.request_id))
        events = await get_events_for_user(session, user.id)

    assert request.status == "PENDING"
    assert request.resulting_mandate_id is None
    assert fetched.status == "PENDING"
    assert any(e.event_type == "AUTHORIZATION_REQUESTED" and e.user_id == str(user.id) for e in events)
    assert any(e.event_type == "CART_CREATED" and e.user_id == str(user.id) for e in events)


async def test_duplicate_pending_request_is_rejected() -> None:
    merchant, product, user = await _create_merchant_with_product()
    cart_id = await _create_cart_with_item(merchant, product, user)

    factory = get_session_factory()
    async with factory() as session:
        terms = _suggested_terms(cart_id, product, max_amount_minor=300_000)
        await create_authorization_request(session, terms)
        await session.commit()

        try:
            await create_authorization_request(session, terms)
            raised = None
        except AgentPayError as exc:
            raised = exc

    assert raised is not None
    assert raised.reason_code == "AUTHORIZATION_ALREADY_PENDING"


async def test_request_authorization_on_frozen_cart_is_rejected() -> None:
    merchant, product, user = await _create_merchant_with_product()
    cart_id = await _create_cart_with_item(merchant, product, user)

    factory = get_session_factory()
    async with factory() as session:
        terms = _suggested_terms(cart_id, product, max_amount_minor=300_000)
        request = await create_authorization_request(session, terms)
        await session.commit()

        approved = await approve_authorization_request(
            session,
            uuid.UUID(request.request_id),
            ApproveAuthorizationRequest(
                product_type=product.name, max_amount_minor=300_000, allowed_categories=[product.category]
            ),
        )
        await session.commit()

        await request_checkout(session, cart_id, approved.resulting_mandate_id)
        await session.commit()

        terms_2 = _suggested_terms(cart_id, product, max_amount_minor=300_000)
        try:
            await create_authorization_request(session, terms_2)
            raised = None
        except AgentPayError as exc:
            raised = exc

    assert raised is not None
    assert raised.reason_code == "CART_NOT_OPEN"


async def test_reject_flow_creates_no_mandate() -> None:
    merchant, product, user = await _create_merchant_with_product()
    cart_id = await _create_cart_with_item(merchant, product, user)

    factory = get_session_factory()
    async with factory() as session:
        terms = _suggested_terms(cart_id, product, max_amount_minor=300_000)
        request = await create_authorization_request(session, terms)
        await session.commit()

        rejected = await reject_authorization_request(session, uuid.UUID(request.request_id))
        await session.commit()

        events = await get_events_for_user(session, user.id)

    assert rejected.status == "REJECTED"
    assert rejected.resulting_mandate_id is None
    assert any(e.event_type == "AUTHORIZATION_REJECTED" for e in events)


async def test_approve_as_is_produces_a_valid_signed_mandate_and_checkout_succeeds() -> None:
    merchant, product, user = await _create_merchant_with_product(price_minor=200_000)
    cart_id = await _create_cart_with_item(merchant, product, user)

    factory = get_session_factory()
    async with factory() as session:
        terms = _suggested_terms(cart_id, product, max_amount_minor=300_000)
        request = await create_authorization_request(session, terms)
        await session.commit()

        approved = await approve_authorization_request(
            session,
            uuid.UUID(request.request_id),
            ApproveAuthorizationRequest(
                product_type=product.name, max_amount_minor=300_000, allowed_categories=[product.category]
            ),
        )
        await session.commit()

        assert approved.status == "APPROVED"
        assert approved.resulting_mandate_id is not None

        mandate_row = await get_mandate_by_business_id(session, approved.resulting_mandate_id)
        signed_mandate = to_signed_mandate(mandate_row)
        verification = verify_mandate(signed_mandate, get_settings().ed25519_public_key_b64, current_status=mandate_row.status)
        assert verification.valid is True

        checkout_result = await request_checkout(session, cart_id, approved.resulting_mandate_id)
        await session.commit()

    assert checkout_result.cart.status == "FROZEN"


async def test_approve_with_edited_terms_enforces_the_edit_not_claudes_ask() -> None:
    """
    The trust-critical case: Claude asks to be allowed to buy in
    "accessories", the human's Edit drops that category, and the resulting
    mandate enforces the human's edit -- checkout against it is rejected.
    """
    merchant, product, user = await _create_merchant_with_product(category="accessories")
    cart_id = await _create_cart_with_item(merchant, product, user)

    factory = get_session_factory()
    async with factory() as session:
        terms = _suggested_terms(cart_id, product, max_amount_minor=300_000)
        request = await create_authorization_request(session, terms)
        await session.commit()

        # The human edits: same product_type/amount, but a DIFFERENT
        # (non-matching) allowed category than Claude asked for.
        approved = await approve_authorization_request(
            session,
            uuid.UUID(request.request_id),
            ApproveAuthorizationRequest(
                product_type=product.name, max_amount_minor=300_000, allowed_categories=["audio"]
            ),
        )
        await session.commit()

        mandate_row = await get_mandate_by_business_id(session, approved.resulting_mandate_id)
        signed_mandate = to_signed_mandate(mandate_row)
        assert signed_mandate.payload.allowed_categories == ["audio"]

        try:
            await request_checkout(session, cart_id, approved.resulting_mandate_id)
            raised = None
        except AgentPayError as exc:
            raised = exc

    assert raised is not None
    assert raised.reason_code == "MANDATE_CATEGORY_FORBIDDEN"


async def test_approve_with_lowered_cap_enforces_the_edit() -> None:
    """Same trust property, for the spending cap: the human's lowered max_amount_minor is what's enforced."""
    merchant, product, user = await _create_merchant_with_product(price_minor=200_000)
    cart_id = await _create_cart_with_item(merchant, product, user)

    factory = get_session_factory()
    async with factory() as session:
        terms = _suggested_terms(cart_id, product, max_amount_minor=300_000)
        request = await create_authorization_request(session, terms)
        await session.commit()

        # Human edits the cap down below the cart's actual 200_000 subtotal.
        approved = await approve_authorization_request(
            session,
            uuid.UUID(request.request_id),
            ApproveAuthorizationRequest(
                product_type=product.name, max_amount_minor=100_000, allowed_categories=[product.category]
            ),
        )
        await session.commit()

        try:
            await request_checkout(session, cart_id, approved.resulting_mandate_id)
            raised = None
        except AgentPayError as exc:
            raised = exc

    assert raised is not None
    assert raised.reason_code == "MANDATE_AMOUNT_EXCEEDED"
