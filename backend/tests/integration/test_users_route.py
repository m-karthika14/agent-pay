"""
Purpose: Integration tests for the demo user identity route (POST
/api/users), exercised through the real FastAPI app against the real
PostgreSQL database.

The storefront needs a real user_id before it can create a cart (carts
require an existing User row), well before any mandate exists -- this
route resolves that by email, idempotently.
"""
import uuid

import httpx
from httpx import ASGITransport

from app.main import app


async def _client() -> httpx.AsyncClient:
    transport = ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")


async def test_create_user_returns_a_user_id() -> None:
    email = f"buyer-{uuid.uuid4().hex[:8]}@agentpay.test"

    async with await _client() as client:
        response = await client.post("/api/users", json={"email": email, "name": "Test Buyer"})

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["email"] == email
    assert body["data"]["name"] == "Test Buyer"
    uuid.UUID(body["data"]["user_id"])


async def test_same_email_returns_same_user_id() -> None:
    email = f"buyer-{uuid.uuid4().hex[:8]}@agentpay.test"

    async with await _client() as client:
        first = await client.post("/api/users", json={"email": email, "name": "First Name"})
        second = await client.post("/api/users", json={"email": email, "name": "Second Name"})

    assert first.json()["data"]["user_id"] == second.json()["data"]["user_id"]


async def test_default_name_used_when_omitted() -> None:
    email = f"buyer-{uuid.uuid4().hex[:8]}@agentpay.test"

    async with await _client() as client:
        response = await client.post("/api/users", json={"email": email})

    assert response.status_code == 200
    assert response.json()["data"]["name"] == "Storefront Buyer"
