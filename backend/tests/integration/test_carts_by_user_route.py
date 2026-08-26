"""
Purpose: Integration tests for GET /api/carts/by-user/{user_id} (plan.md
Section 19 -- login), exercised through the real FastAPI app against the
real PostgreSQL database.

This is what lets a freshly-logged-in browser discover a cart Claude
already created via MCP under the same user_id, since a fresh browser
session has no cart_id of its own stored locally.
"""
import uuid
from datetime import UTC, datetime, timedelta

import httpx
from httpx import ASGITransport

from app.db.models.inventory import Inventory
from app.db.models.merchant import Merchant
from app.db.models.product import Product
from app.db.models.user import User
from app.db.session import get_session_factory
from app.main import app
from app.mandates.service import create_mandate
from app.schemas.mandate import MandateIntent, MandatePayload


async def _client() -> httpx.AsyncClient:
    transport = ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")


async def _create_fixture_data():
    factory = get_session_factory()
    async with factory() as session:
        unique = uuid.uuid4().hex[:8]
        merchant = Merchant(slug=f"cart-by-user-test-{unique}", name="Cart By User Test Merchant", currency="INR")
        user = User(email=f"cart-by-user-{unique}@agentpay.test", name="Cart By User Test Buyer")
        session.add_all([merchant, user])
        await session.flush()

        product = Product(
            merchant_id=merchant.id,
            sku=f"SKU-{unique}",
            name="Test Widget",
            description="A widget used only in tests.",
            price_minor=10_000,
            currency="INR",
            category="electronics",
            is_active=True,
        )
        session.add(product)
        await session.flush()
        session.add(Inventory(product_id=product.id, quantity=5, reserved_quantity=0))
        await session.commit()
        return merchant, product, user


async def _create_mandate_for(merchant, user) -> str:
    payload = MandatePayload(
        mandate_id=f"M-{uuid.uuid4().hex[:8]}",
        merchant_id=str(merchant.id),
        currency="INR",
        max_amount=500_000,
        allowed_categories=["electronics"],
        allow_addons=False,
        delivery_requirement="under_3_days",
        single_use=True,
        expires_at=datetime.now(UTC) + timedelta(days=1),
        intent=MandateIntent(product_type="test widget"),
    )
    factory = get_session_factory()
    async with factory() as session:
        await create_mandate(session, payload, user.id, merchant.id)
        await session.commit()
    return payload.mandate_id


async def test_no_open_cart_returns_null() -> None:
    _merchant, _product, user = await _create_fixture_data()

    async with await _client() as client:
        response = await client.get(f"/api/carts/by-user/{user.id}")

    assert response.status_code == 200
    assert response.json()["data"] is None


async def test_finds_a_cart_created_elsewhere_under_the_same_user() -> None:
    """Simulates Claude/MCP creating a cart, then the browser discovering it by user_id."""
    merchant, product, user = await _create_fixture_data()

    async with await _client() as client:
        create_response = await client.post(
            "/api/carts", json={"user_id": str(user.id), "merchant_id": str(merchant.id), "currency": "INR"}
        )
        cart_id = create_response.json()["data"]["cart_id"]
        await client.post(f"/api/carts/{cart_id}/items", json={"product_id": str(product.id), "quantity": 1})

        response = await client.get(f"/api/carts/by-user/{user.id}")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["cart_id"] == cart_id
    assert data["items"][0]["product_id"] == str(product.id)


async def test_frozen_cart_is_not_returned() -> None:
    merchant, product, user = await _create_fixture_data()
    mandate_id = await _create_mandate_for(merchant, user)

    async with await _client() as client:
        create_response = await client.post(
            "/api/carts", json={"user_id": str(user.id), "merchant_id": str(merchant.id), "currency": "INR"}
        )
        cart_id = create_response.json()["data"]["cart_id"]
        await client.post(f"/api/carts/{cart_id}/items", json={"product_id": str(product.id), "quantity": 1})
        checkout_response = await client.post(
            "/api/checkout/request", json={"cart_id": cart_id, "mandate_id": mandate_id}
        )
        assert checkout_response.status_code == 200

        response = await client.get(f"/api/carts/by-user/{user.id}")

    assert response.status_code == 200
    assert response.json()["data"] is None
