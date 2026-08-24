"""
Purpose: Integration tests for the Phase 2 catalog + mutable-cart API,
exercised through the real FastAPI app (ASGI, in-process) against the real
PostgreSQL database.

Checkout/freeze-specific tests (request_checkout, cart hash) are added here
in Phase 3 per plan.md Section 4's file layout; this phase only covers the
mutable cart lifecycle (create/add/update/remove/get) and catalog reads.

Each test creates its own merchant/product/inventory/user fixtures with
unique identifiers, independent of the seeded UrbanNest data, so this suite
never depends on scripts/seed_database.py having been run.
"""
import uuid

import httpx
from httpx import ASGITransport

from app.db.models.inventory import Inventory
from app.db.models.merchant import Merchant
from app.db.models.product import Product
from app.db.models.user import User
from app.db.session import get_session_factory
from app.main import app


async def _create_fixture_data():
    """Create an isolated merchant + product + inventory + user for one test."""
    factory = get_session_factory()
    async with factory() as session:
        unique = uuid.uuid4().hex[:8]
        merchant = Merchant(slug=f"test-merchant-{unique}", name="Test Merchant", currency="INR")
        user = User(email=f"test-{unique}@agentpay.test", name="Test User")
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


async def _client() -> httpx.AsyncClient:
    """Build an httpx client that talks to the FastAPI app in-process (no real server)."""
    transport = ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")


async def test_list_and_get_product() -> None:
    merchant, product, _user = await _create_fixture_data()

    async with await _client() as client:
        list_response = await client.get("/api/products")
        assert list_response.status_code == 200
        body = list_response.json()
        assert body["success"] is True
        assert any(p["product_id"] == str(product.id) for p in body["data"])

        get_response = await client.get(f"/api/products/{product.id}")
        assert get_response.status_code == 200
        product_data = get_response.json()["data"]
        assert product_data["name"] == "Test Widget"
        assert product_data["merchant_id"] == str(merchant.id)
        assert product_data["availability"] == "in_stock"
        assert product_data["delivery"]
        assert product_data["return_policy"]


async def test_get_unknown_product_returns_404() -> None:
    async with await _client() as client:
        response = await client.get(f"/api/products/{uuid.uuid4()}")

    assert response.status_code == 404
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "PRODUCT_NOT_FOUND"


async def test_get_product_inventory() -> None:
    _merchant, product, _user = await _create_fixture_data()

    async with await _client() as client:
        response = await client.get(f"/api/products/{product.id}/inventory")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["quantity"] == 5
    assert data["reserved_quantity"] == 0
    assert data["available_quantity"] == 5


async def test_full_cart_lifecycle() -> None:
    """create_cart -> add_to_cart (merge) -> update -> remove, per plan.md Section 10."""
    merchant, product, user = await _create_fixture_data()

    async with await _client() as client:
        create_response = await client.post(
            "/api/carts",
            json={"user_id": str(user.id), "merchant_id": str(merchant.id), "currency": "INR"},
        )
        assert create_response.status_code == 200
        cart = create_response.json()["data"]
        assert cart["status"] == "OPEN"
        assert cart["subtotal_minor"] == 0
        cart_id = cart["cart_id"]

        # Add 1, then add 2 more of the same product -- must merge into one line.
        await client.post(f"/api/carts/{cart_id}/items", json={"product_id": str(product.id), "quantity": 1})
        add_response = await client.post(
            f"/api/carts/{cart_id}/items", json={"product_id": str(product.id), "quantity": 2}
        )
        assert add_response.status_code == 200
        cart = add_response.json()["data"]
        assert len(cart["items"]) == 1
        assert cart["items"][0]["quantity"] == 3
        assert cart["subtotal_minor"] == 30_000
        item_id = cart["items"][0]["item_id"]

        # Requesting more than available inventory must fail cleanly.
        over_response = await client.patch(
            f"/api/carts/{cart_id}/items/{item_id}", json={"quantity": 999}
        )
        assert over_response.status_code == 400
        assert over_response.json()["error"]["code"] == "INSUFFICIENT_INVENTORY"

        # Update to a valid quantity.
        update_response = await client.patch(
            f"/api/carts/{cart_id}/items/{item_id}", json={"quantity": 2}
        )
        assert update_response.status_code == 200
        assert update_response.json()["data"]["subtotal_minor"] == 20_000

        # get_cart reflects the same state.
        get_response = await client.get(f"/api/carts/{cart_id}")
        assert get_response.json()["data"]["subtotal_minor"] == 20_000

        # Remove the item -- subtotal returns to zero.
        remove_response = await client.delete(f"/api/carts/{cart_id}/items/{item_id}")
        assert remove_response.status_code == 200
        cart = remove_response.json()["data"]
        assert cart["items"] == []
        assert cart["subtotal_minor"] == 0


async def test_get_unknown_cart_returns_404() -> None:
    async with await _client() as client:
        response = await client.get(f"/api/carts/{uuid.uuid4()}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CART_NOT_FOUND"
