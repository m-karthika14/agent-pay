"""
Purpose: Integration tests for POST /api/auth/login (plan.md Section 19 --
buyer identity), exercised through the real FastAPI app against the real
PostgreSQL database.

Covers app.auth.service.login_or_claim's three cases: brand-new email
(signup), an existing password-less user created via POST /api/users
(claimed on first login -- this is how every user created before the login
page existed, including Claude/MCP's own get_or_create_user() calls, gets
a password without any separate backfill step), and a normal existing
login with a password already set.
"""
import uuid

import httpx
from httpx import ASGITransport

from app.main import app


async def _client() -> httpx.AsyncClient:
    transport = ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")


async def test_login_with_new_email_creates_the_user() -> None:
    email = f"newbuyer-{uuid.uuid4().hex[:8]}@agentpay.test"

    async with await _client() as client:
        response = await client.post("/api/auth/login", json={"email": email, "password": "hunter2", "name": "New Buyer"})

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["email"] == email
    assert body["name"] == "New Buyer"
    uuid.UUID(body["user_id"])


async def test_login_again_with_correct_password_returns_same_user() -> None:
    email = f"repeatbuyer-{uuid.uuid4().hex[:8]}@agentpay.test"

    async with await _client() as client:
        first = await client.post("/api/auth/login", json={"email": email, "password": "correct-horse"})
        second = await client.post("/api/auth/login", json={"email": email, "password": "correct-horse"})

    assert first.json()["data"]["user_id"] == second.json()["data"]["user_id"]


async def test_login_with_wrong_password_is_rejected() -> None:
    email = f"wrongpass-{uuid.uuid4().hex[:8]}@agentpay.test"

    async with await _client() as client:
        await client.post("/api/auth/login", json={"email": email, "password": "the-real-password"})
        response = await client.post("/api/auth/login", json={"email": email, "password": "a-guess"})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"


async def test_password_less_user_claims_a_password_on_first_login() -> None:
    """A user created via POST /api/users (e.g. by Claude/MCP) has no password yet -- logging in for the first time claims one."""
    email = f"claimed-{uuid.uuid4().hex[:8]}@agentpay.test"

    async with await _client() as client:
        create_response = await client.post("/api/users", json={"email": email, "name": "MCP-created Buyer"})
        created_user_id = create_response.json()["data"]["user_id"]

        login_response = await client.post("/api/auth/login", json={"email": email, "password": "my-new-password"})
        assert login_response.status_code == 200
        assert login_response.json()["data"]["user_id"] == created_user_id

        # The claimed password must now actually be enforced.
        wrong_password_response = await client.post(
            "/api/auth/login", json={"email": email, "password": "not-it"}
        )
        assert wrong_password_response.status_code == 401

        right_password_response = await client.post(
            "/api/auth/login", json={"email": email, "password": "my-new-password"}
        )
        assert right_password_response.status_code == 200
