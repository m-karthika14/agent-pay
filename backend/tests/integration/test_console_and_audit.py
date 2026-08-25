"""
Purpose: Integration tests for Phase 11's Merchant Console backend --
GET /api/transactions/{id}/trace's richer response, GET /api/audit/*, and
GET /api/console/* -- exercised through the real FastAPI app against the
real PostgreSQL database.

Mirrors tests/integration/test_webhooks.py's fixture pattern: Razorpay's
create_order() is mocked (this project's own order/transaction persistence
is under test, not Razorpay's API).
"""
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import httpx
import pytest
from httpx import ASGITransport
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models.inventory import Inventory
from app.db.models.merchant import Merchant
from app.db.models.product import Product
from app.db.models.transaction import Transaction
from app.db.models.user import User
from app.db.session import get_session_factory
from app.main import app
from app.mandates.service import create_mandate
from app.schemas.mandate import MandateIntent, MandatePayload


@pytest.fixture
def razorpay_test_secrets(monkeypatch):
    """Configure known Test Mode-shaped secrets for the duration of one test."""
    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test_fake_key_id")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "fake_key_secret_for_tests")
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", "fake_webhook_secret_for_tests")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def _client() -> httpx.AsyncClient:
    transport = ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")


async def _create_fixture_data():
    factory = get_session_factory()
    async with factory() as session:
        unique = uuid.uuid4().hex[:8]
        merchant = Merchant(slug=f"console-test-{unique}", name="Console Test Merchant", currency="INR")
        user = User(email=f"console-test-{unique}@agentpay.test", name="Console Test User")
        session.add_all([merchant, user])
        await session.flush()

        product = Product(
            merchant_id=merchant.id, sku=f"SKU-{unique}", name="Console Test Widget", description="d",
            price_minor=25_000, currency="INR", category="electronics", is_active=True,
        )
        session.add(product)
        await session.flush()
        session.add(Inventory(product_id=product.id, quantity=5, reserved_quantity=0))
        await session.commit()
        return merchant, product, user


async def _create_mandate_for(merchant, user) -> str:
    payload = MandatePayload(
        mandate_id=f"M-console-{uuid.uuid4().hex[:8]}",
        merchant_id=str(merchant.id),
        currency="INR",
        max_amount=500_000,
        allowed_categories=["electronics"],
        allow_addons=False,
        delivery_requirement="under_3_days",
        single_use=True,
        expires_at=datetime.now(UTC) + timedelta(days=1),
        intent=MandateIntent(product_type="console test widget", notes="for console tests"),
    )
    factory = get_session_factory()
    async with factory() as session:
        await create_mandate(session, payload, user.id, merchant.id)
        await session.commit()
    return payload.mandate_id


async def _create_completed_checkout(client: httpx.AsyncClient, merchant, product, user, mandate_id: str) -> uuid.UUID:
    """Create+freeze a cart and complete checkout (mocked Razorpay order). Returns the transaction's internal id."""
    create_response = await client.post(
        "/api/carts", json={"user_id": str(user.id), "merchant_id": str(merchant.id), "currency": "INR"}
    )
    cart_id = create_response.json()["data"]["cart_id"]
    await client.post(f"/api/carts/{cart_id}/items", json={"product_id": str(product.id), "quantity": 1})
    checkout_response = await client.post(
        "/api/checkout/request", json={"cart_id": cart_id, "mandate_id": mandate_id}
    )
    assert checkout_response.status_code == 200

    fake_order_id = f"order_console_{uuid.uuid4().hex[:8]}"
    with patch("app.payments.checkout.create_order", return_value={"id": fake_order_id}):
        complete_response = await client.post(f"/api/checkout/{cart_id}/complete", json={"mandate_id": mandate_id})
    assert complete_response.status_code == 200
    order_id = complete_response.json()["data"]["order_id"]

    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(select(Transaction).where(Transaction.order_id == uuid.UUID(order_id)))
        transaction = result.scalar_one()
        return transaction.id


async def test_transaction_trace_includes_order_cart_mandate_and_buyer(razorpay_test_secrets) -> None:
    """Phase 11: GET /api/transactions/{id}/trace returns everything the Transaction view needs."""
    merchant, product, user = await _create_fixture_data()
    mandate_id = await _create_mandate_for(merchant, user)

    async with await _client() as client:
        transaction_id = await _create_completed_checkout(client, merchant, product, user, mandate_id)
        response = await client.get(f"/api/transactions/{transaction_id}/trace")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["transaction"]["transaction_id"] == str(transaction_id)
    assert data["order"]["mandate_id"] == mandate_id
    assert data["cart"]["items"][0]["product_name"] == "Console Test Widget"
    assert data["mandate"]["mandate_id"] == mandate_id
    assert data["mandate"]["product_type"] == "console test widget"
    assert data["buyer"]["email"] == user.email
    assert any(event["event_type"] == "CART_FROZEN" for event in data["events"])
    assert any(event["event_type"] == "RAZORPAY_ORDER_CREATED" for event in data["events"])


async def test_audit_events_for_transaction_carry_hash_chain_fields(razorpay_test_secrets) -> None:
    """Phase 11: GET /api/audit/{id} exposes the Audit viewer's exact fields (plan.md Section 24)."""
    merchant, product, user = await _create_fixture_data()
    mandate_id = await _create_mandate_for(merchant, user)

    async with await _client() as client:
        transaction_id = await _create_completed_checkout(client, merchant, product, user, mandate_id)
        response = await client.get(f"/api/audit/{transaction_id}")

    assert response.status_code == 200
    events = response.json()["data"]
    assert len(events) >= 2
    for event in events:
        assert "event_hash" in event
        assert "reason_code" in event
    # Chain order: each event's previous_hash equals the prior event's event_hash.
    for earlier, later in zip(events, events[1:]):
        assert later["previous_hash"] == earlier["event_hash"]


async def test_verify_audit_chain_reports_valid(razorpay_test_secrets) -> None:
    """Phase 11: GET /api/audit/{id}/verify reports the (real) chain as valid."""
    merchant, product, user = await _create_fixture_data()
    mandate_id = await _create_mandate_for(merchant, user)

    async with await _client() as client:
        transaction_id = await _create_completed_checkout(client, merchant, product, user, mandate_id)
        response = await client.get(f"/api/audit/{transaction_id}/verify")

    assert response.status_code == 200
    result = response.json()["data"]
    assert result["valid"] is True
    assert result["events_checked"] > 0


async def test_verify_audit_chain_unknown_transaction_404s(razorpay_test_secrets) -> None:
    async with await _client() as client:
        response = await client.get(f"/api/audit/{uuid.uuid4()}/verify")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "TRANSACTION_NOT_FOUND"


async def test_console_summary_reflects_recent_transaction(razorpay_test_secrets) -> None:
    merchant, product, user = await _create_fixture_data()
    mandate_id = await _create_mandate_for(merchant, user)

    async with await _client() as client:
        transaction_id = await _create_completed_checkout(client, merchant, product, user, mandate_id)
        response = await client.get("/api/console/summary")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total_transactions"] >= 1
    assert data["total_mandates"] >= 1
    assert data["total_audit_events"] >= 1
    assert any(row["transaction_id"] == str(transaction_id) for row in data["recent_transactions"])


async def test_console_events_returns_recent_feed(razorpay_test_secrets) -> None:
    merchant, product, user = await _create_fixture_data()
    mandate_id = await _create_mandate_for(merchant, user)

    async with await _client() as client:
        await _create_completed_checkout(client, merchant, product, user, mandate_id)
        response = await client.get("/api/console/events?limit=5")

    assert response.status_code == 200
    events = response.json()["data"]
    assert 0 < len(events) <= 5


async def test_console_metrics_returns_a_structurally_valid_response() -> None:
    """available reflects whether eval/metrics.py has been run -- either state is a valid response, never a crash."""
    async with await _client() as client:
        response = await client.get("/api/console/metrics")

    assert response.status_code == 200
    data = response.json()["data"]
    assert isinstance(data["available"], bool)
    if data["available"]:
        assert data["metrics"] is not None
    else:
        assert data["metrics"] is None
