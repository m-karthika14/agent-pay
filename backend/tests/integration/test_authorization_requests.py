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
import hashlib
import hmac
import json
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from httpx import ASGITransport

from app.agents.merchant.nodes import _CandidateProposal, _CandidateProposalList
from app.authorization.service import (
    approve_authorization_request,
    create_authorization_request,
    get_authorization_request,
    reject_authorization_request,
)
from app.carts.service import add_cart_item, create_cart, get_cart_by_mandate
from app.core.config import get_settings
from app.db.models.inventory import Inventory
from app.db.models.mandate import Mandate, MandateStatus
from app.db.models.merchant import Merchant
from app.db.models.product import Product
from app.db.models.user import User
from app.db.session import get_session_factory
from app.intent.models import IntentDecisionType, _IntentClassification
from app.main import app
from app.mandates.service import create_mandate, get_mandate_by_business_id, to_signed_mandate
from app.schemas.authorization import ApproveAuthorizationRequest, RequestAuthorizationInput
from app.schemas.common import AgentPayError
from app.schemas.mandate import MandateIntent, MandatePayload
from app.security.mandate_verifier import verify_mandate
from app.services.audit_service import get_events_for_user
from app.services.checkout_service import request_checkout

MERCHANT_PATCH_TARGET = "app.agents.merchant.nodes.classify_with_schema"
INTENT_PATCH_TARGET = "app.intent.gate.classify_with_schema"
WEBHOOK_SECRET = "fake_webhook_secret_for_tests"


@pytest.fixture
def razorpay_test_secrets(monkeypatch):
    """Configure known Test Mode-shaped secrets for the duration of one test."""
    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test_fake_key_id")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "fake_key_secret_for_tests")
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", WEBHOOK_SECRET)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")


def _sign_webhook(body: bytes) -> str:
    return hmac.new(key=WEBHOOK_SECRET.encode("utf-8"), msg=body, digestmod=hashlib.sha256).hexdigest()


def _payment_captured_payload(razorpay_order_id: str, razorpay_payment_id: str) -> bytes:
    return json.dumps(
        {
            "event": "payment.captured",
            "payload": {
                "payment": {"entity": {"id": razorpay_payment_id, "order_id": razorpay_order_id, "status": "captured"}}
            },
        }
    ).encode("utf-8")


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


async def test_checkout_with_no_mandate_id_resolves_the_approved_one() -> None:
    """Phase 2.1: request_checkout(cart_id) with no mandate_id, after an as-is approval, succeeds and freezes the cart."""
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

        checkout_result = await request_checkout(session, cart_id)
        await session.commit()

    assert checkout_result.cart.status == "FROZEN"
    assert checkout_result.cart.mandate_id == approved.resulting_mandate_id


async def test_rest_route_accepts_checkout_request_with_no_mandate_id() -> None:
    """
    Phase 4.2: POST /api/checkout/request itself (not just the service
    function) accepts an omitted mandate_id -- needed by the storefront's
    own CheckoutPage, which must be able to try the cart's already-approved
    Claude authorization first, before ever creating a second, redundant
    mandate of its own.
    """
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

    async with await _client() as client:
        response = await client.post("/api/checkout/request", json={"cart_id": str(cart_id)})

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["cart"]["status"] == "FROZEN"
    assert body["data"]["cart"]["mandate_id"] == approved.resulting_mandate_id


async def test_checkout_with_no_mandate_id_and_no_approval_is_rejected() -> None:
    """Phase 2.1: request_checkout(cart_id) before any approval (or with none at all) fails loud, not silently."""
    merchant, product, user = await _create_merchant_with_product()
    cart_id = await _create_cart_with_item(merchant, product, user)

    factory = get_session_factory()
    async with factory() as session:
        # No authorization request at all yet.
        try:
            await request_checkout(session, cart_id)
            raised = None
        except AgentPayError as exc:
            raised = exc
    assert raised is not None
    assert raised.reason_code == "NO_APPROVED_AUTHORIZATION"

    async with factory() as session:
        # A PENDING (not yet APPROVED) request also isn't enough.
        terms = _suggested_terms(cart_id, product, max_amount_minor=300_000)
        await create_authorization_request(session, terms)
        await session.commit()

        try:
            await request_checkout(session, cart_id)
            raised = None
        except AgentPayError as exc:
            raised = exc

    assert raised is not None
    assert raised.reason_code == "NO_APPROVED_AUTHORIZATION"


async def test_checkout_with_no_mandate_id_reuses_frozen_carts_own_mandate_on_retry() -> None:
    """
    Phase 2.1's safety property: once a cart is FROZEN, a second cart-only
    request_checkout() call must reuse that SAME mandate (via cart.mandate_id)
    and hit the existing IDEMPOTENCY_DUPLICATE block -- never silently
    re-resolve to some other APPROVED request for the same cart.
    """
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

        await request_checkout(session, cart_id)
        await session.commit()

        try:
            await request_checkout(session, cart_id)
            raised = None
        except AgentPayError as exc:
            raised = exc

    assert raised is not None
    assert raised.reason_code == "IDEMPOTENCY_DUPLICATE"
    assert approved.resulting_mandate_id is not None  # sanity: this test actually exercised the approved path


async def test_get_cart_by_mandate_finds_cart_before_checkout_is_requested() -> None:
    """
    Reported live bug: right after a human approves a Claude-initiated
    authorization request, the mandate is ACTIVE and signed immediately,
    but the cart Claude already built stays OPEN and unlinked until Claude's
    own later request_checkout() call -- a real, populated cart, invisible
    to a human watching the AI Activity page by mandate_id in exactly that
    (normal, often multi-minute) window. get_cart_by_mandate() must fall
    back to the cart behind the approved request, not just Cart.mandate_id.
    """
    merchant, product, user = await _create_merchant_with_product(price_minor=799_900)
    cart_id = await _create_cart_with_item(merchant, product, user)

    factory = get_session_factory()
    async with factory() as session:
        terms = _suggested_terms(cart_id, product, max_amount_minor=899_900)
        request = await create_authorization_request(session, terms)
        await session.commit()

        approved = await approve_authorization_request(
            session,
            uuid.UUID(request.request_id),
            ApproveAuthorizationRequest(
                product_type=product.name, max_amount_minor=899_900, allowed_categories=[product.category]
            ),
        )
        await session.commit()

        mandate_row = await get_mandate_by_business_id(session, approved.resulting_mandate_id)
        assert mandate_row.status == MandateStatus.ACTIVE  # signed, but no checkout requested yet

        found_cart = await get_cart_by_mandate(session, mandate_row.id)

    assert found_cart is not None
    assert found_cart.cart_id == str(cart_id)
    assert len(found_cart.items) == 1
    assert found_cart.items[0].product_name == product.name


async def test_authorize_agent_first_flow_still_works_with_explicit_mandate_id() -> None:
    """
    Confirms the pre-existing, still-supported flow: a human authorizes via
    /authorize-agent BEFORE any cart exists (so no AuthorizationRequest row
    is ever created), and Claude passes that mandate_id explicitly --
    exactly as it always could, unaffected by mandate_id becoming optional.
    """
    merchant, product, user = await _create_merchant_with_product(price_minor=200_000)

    factory = get_session_factory()
    async with factory() as session:
        payload = MandatePayload(
            mandate_id=f"M-authfirst-{uuid.uuid4().hex[:8]}",
            merchant_id=str(merchant.id),
            currency="INR",
            max_amount=300_000,
            allowed_categories=[product.category],
            allow_addons=False,
            delivery_requirement="under_3_days",
            single_use=True,
            expires_at=datetime.now(UTC) + timedelta(days=1),
            intent=MandateIntent(product_type=product.name),
        )
        await create_mandate(session, payload, user.id, merchant.id)
        await session.commit()

    cart_id = await _create_cart_with_item(merchant, product, user)

    factory = get_session_factory()
    async with factory() as session:
        checkout_result = await request_checkout(session, cart_id, payload.mandate_id)
        await session.commit()

    assert checkout_result.cart.status == "FROZEN"


async def test_edited_mandate_invalidates_a_cart_built_for_the_original_ask() -> None:
    """
    Phase 3: the mandate is the buyer's spending authority, not a snapshot
    of one cart -- so an approval that lowers the cap must invalidate any
    cart that was already built expecting the higher, originally-requested
    one. Claude asks for Rs 3,000; the cart is already at Rs 2,500 (built
    while that ask was still pending); the human approves at only Rs 2,000
    instead. request_checkout must reject the existing cart outright, not
    silently succeed because the cart happens to predate the lower cap.
    """
    merchant, product, user = await _create_merchant_with_product(price_minor=250_000)
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
                product_type=product.name, max_amount_minor=200_000, allowed_categories=[product.category]
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


async def test_full_demo_scenario_upsell_within_headroom_then_paid_order(razorpay_test_secrets) -> None:
    """
    Phase 3's end-to-end proof, as a real automated test rather than a
    one-off manual script: earbuds (Rs 2,299, audio) -> Claude asks for
    Rs 3,000 with audio+accessories -> human approves as-is -> mandate is
    ACTIVE, not consumed, immediately after approval -> Merchant Agent
    proposes the Rs 249 case -> Rs 2,299 + Rs 249 = Rs 2,548 <= Rs 3,000 ->
    ALLOWED -> cart frozen at Rs 2,548, mandate still ACTIVE (not consumed
    by freezing) -> Razorpay order created (mocked) -> webhook reports
    payment.captured -> only NOW is the mandate CONSUMED.
    """
    unique = uuid.uuid4().hex[:8]
    factory = get_session_factory()
    async with factory() as session:
        merchant = Merchant(slug=f"demo-{unique}", name=f"Demo Merchant {unique}", currency="INR")
        user = User(email=f"demo-{unique}@agentpay.test", name="Demo Buyer")
        session.add_all([merchant, user])
        await session.flush()

        earbuds = Product(
            merchant_id=merchant.id, sku=f"DEMO-EARBUDS-{unique}", name="Wireless Earbuds", description="d",
            price_minor=229_900, currency="INR", category="audio", is_active=True,
        )
        case = Product(
            merchant_id=merchant.id, sku=f"DEMO-CASE-{unique}", name="Protective Case", description="d",
            price_minor=24_900, currency="INR", category="accessories", is_active=True,
        )
        session.add_all([earbuds, case])
        await session.flush()
        session.add_all(
            [
                Inventory(product_id=earbuds.id, quantity=10, reserved_quantity=0),
                Inventory(product_id=case.id, quantity=10, reserved_quantity=0),
            ]
        )
        await session.commit()

        cart = await create_cart(session, user.id, merchant.id, "INR")
        cart_id = uuid.UUID(cart.cart_id)
        await add_cart_item(session, cart_id, earbuds.id, 1)
        await session.commit()

        request = await create_authorization_request(
            session,
            RequestAuthorizationInput(
                cart_id=str(cart_id),
                product_type="wireless earbuds",
                max_amount_minor=300_000,
                allowed_categories=["audio", "accessories"],
                reason="Matches the buyer's Rs 3,000 earbuds ask, with room for a relevant add-on.",
            ),
        )
        await session.commit()

        approved = await approve_authorization_request(
            session,
            uuid.UUID(request.request_id),
            ApproveAuthorizationRequest(
                product_type="wireless earbuds", max_amount_minor=300_000, allowed_categories=["audio", "accessories"]
            ),
        )
        await session.commit()

        mandate_row = await get_mandate_by_business_id(session, approved.resulting_mandate_id)
        assert mandate_row.status == MandateStatus.ACTIVE  # not consumed merely by approval

        candidates = _CandidateProposalList(
            candidates=[
                _CandidateProposal(
                    product_id=str(case.id), quantity=1, reason="A protective case pairs well with these earbuds.",
                    estimated_value_add_minor=24_900,
                )
            ]
        )
        classification = _IntentClassification(decision=IntentDecisionType.ALLOW, confidence=0.95, reason="Consistent with intent.")

        with (
            patch(MERCHANT_PATCH_TARGET, new=AsyncMock(return_value=candidates)),
            patch(INTENT_PATCH_TARGET, new=AsyncMock(return_value=classification)),
        ):
            # Cart-only call (Phase 2.1) -- Claude never has to carry the mandate_id forward itself.
            checkout_result = await request_checkout(session, cart_id)
        await session.commit()

        assert checkout_result.proposal is not None
        assert checkout_result.proposal.status.value == "PROPOSAL_ALLOWED"
        assert checkout_result.cart.subtotal_minor == 254_800  # Rs 2,299 + Rs 249
        assert checkout_result.cart.status == "FROZEN"

        await session.refresh(mandate_row)
        assert mandate_row.status == MandateStatus.ACTIVE  # not consumed merely by freezing

    fake_order_id = f"order_demo_{unique}"
    fake_payment_id = f"pay_demo_{unique}"
    with patch("app.payments.checkout.create_order", return_value={"id": fake_order_id}):
        async with await _client() as client:
            complete_response = await client.post(
                f"/api/checkout/{cart_id}/complete", json={"mandate_id": approved.resulting_mandate_id}
            )
    assert complete_response.status_code == 200

    body = _payment_captured_payload(fake_order_id, fake_payment_id)
    signature = _sign_webhook(body)
    async with await _client() as client:
        webhook_response = await client.post(
            "/api/webhooks/razorpay", content=body, headers={"X-Razorpay-Signature": signature}
        )
    assert webhook_response.status_code == 200

    async with factory() as session:
        mandate_row = await get_mandate_by_business_id(session, approved.resulting_mandate_id)
        assert mandate_row.status == MandateStatus.CONSUMED  # only now, at real payment capture
