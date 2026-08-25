"""
Purpose: Integration tests for the mandate REST API (plan.md Section 18 —
Mandate), exercised through the real FastAPI app against the real
PostgreSQL database.

This route was missing until now -- a human buyer states their purchase
intent/constraints here, AgentPay signs and persists a mandate, and the
returned mandate_id is what the buyer hands to Claude (via MCP) to
authorize a purchase on their behalf.
"""
import uuid

import httpx
from httpx import ASGITransport

from app.db.models.merchant import Merchant
from app.db.session import get_session_factory
from app.main import app


async def _client() -> httpx.AsyncClient:
    transport = ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")


async def _create_merchant() -> Merchant:
    factory = get_session_factory()
    async with factory() as session:
        merchant = Merchant(slug=f"mandate-route-test-{uuid.uuid4().hex[:8]}", name="Mandate Route Test Merchant", currency="INR")
        session.add(merchant)
        await session.commit()
        return merchant


def _request_body(merchant: Merchant, **overrides: object) -> dict:
    body = {
        "user_email": f"buyer-{uuid.uuid4().hex[:8]}@agentpay.test",
        "user_name": "Test Buyer",
        "merchant_id": str(merchant.id),
        "currency": "INR",
        "max_amount_minor": 300_000,
        "allowed_categories": ["electronics"],
        "allow_addons": False,
        "delivery_requirement": "under_3_days",
        "single_use": True,
        "expires_in_hours": 24,
        "product_type": "wireless earbuds",
        "notes": "no unnecessary accessories",
    }
    body.update(overrides)
    return body


async def test_create_mandate_returns_signed_mandate_id() -> None:
    merchant = await _create_merchant()

    async with await _client() as client:
        response = await client.post("/api/mandates", json=_request_body(merchant))

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["mandate_id"].startswith("M-")
    assert data["merchant_id"] == str(merchant.id)
    assert data["max_amount_minor"] == 300_000
    assert data["product_type"] == "wireless earbuds"
    assert data["status"] == "ACTIVE"


async def test_create_mandate_with_unknown_merchant_404s() -> None:
    fake_merchant = Merchant(id=uuid.uuid4(), slug="ghost", name="Ghost", currency="INR")

    async with await _client() as client:
        response = await client.post("/api/mandates", json=_request_body(fake_merchant))

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "MERCHANT_NOT_FOUND"


async def test_create_mandate_reuses_existing_user_by_email() -> None:
    merchant = await _create_merchant()
    shared_email = f"repeat-buyer-{uuid.uuid4().hex[:8]}@agentpay.test"

    async with await _client() as client:
        first = await client.post("/api/mandates", json=_request_body(merchant, user_email=shared_email))
        second = await client.post(
            "/api/mandates", json=_request_body(merchant, user_email=shared_email, product_type="smart watch")
        )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["data"]["mandate_id"] != second.json()["data"]["mandate_id"]


async def test_get_mandate_by_business_id() -> None:
    merchant = await _create_merchant()

    async with await _client() as client:
        create_response = await client.post("/api/mandates", json=_request_body(merchant))
        mandate_id = create_response.json()["data"]["mandate_id"]

        get_response = await client.get(f"/api/mandates/{mandate_id}")

    assert get_response.status_code == 200
    assert get_response.json()["data"]["mandate_id"] == mandate_id


async def test_get_unknown_mandate_returns_404() -> None:
    async with await _client() as client:
        response = await client.get("/api/mandates/M-does-not-exist")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "MANDATE_NOT_FOUND"


async def test_verify_mandate_route_reports_valid_for_a_fresh_mandate() -> None:
    merchant = await _create_merchant()

    async with await _client() as client:
        create_response = await client.post("/api/mandates", json=_request_body(merchant))
        mandate_id = create_response.json()["data"]["mandate_id"]

        verify_response = await client.post(f"/api/mandates/{mandate_id}/verify")

    assert verify_response.status_code == 200
    assert verify_response.json()["data"]["valid"] is True


async def test_mandate_audit_events_are_visible_before_any_cart_exists() -> None:
    """GET /api/audit/by-mandate/{id} works from mandate creation, before any checkout is requested."""
    merchant = await _create_merchant()

    async with await _client() as client:
        create_response = await client.post("/api/mandates", json=_request_body(merchant))
        mandate_id = create_response.json()["data"]["mandate_id"]

        events_response = await client.get(f"/api/audit/by-mandate/{mandate_id}")
        cart_response = await client.get(f"/api/carts/by-mandate/{mandate_id}")

    assert events_response.status_code == 200
    events = events_response.json()["data"]
    assert any(event["event_type"] == "MANDATE_CREATED" for event in events)

    assert cart_response.status_code == 200
    assert cart_response.json()["data"] is None
