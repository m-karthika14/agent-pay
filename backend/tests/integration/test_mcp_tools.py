"""
Purpose: Integration tests for the AgentPay MCP server (plan.md Section 17),
exercised through a real MCP ClientSession connected in-process (no real
network port), against the real PostgreSQL database.

Per plan.md Section 17 "Local testing": use MCP's client/session testing
capability rather than only manual/remote testing. This suite drives the
exact same Streamable HTTP transport a real client (Claude) would use and
the exact same tool functions app.mcp.server registers in production
(app.mcp.tools.register_tools), just over an in-process ASGI transport
instead of a live socket, and against a throwaway MCPServer instance rather
than the process-wide singleton (see _mcp_client_session for why).

Razorpay order creation is mocked here exactly as in test_webhooks.py --
this suite is about proving the MCP tool <-> service wiring is correct,
not re-verifying Razorpay's API.
"""
import json
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from app.db.models.inventory import Inventory
from app.db.models.merchant import Merchant
from app.db.models.product import Product
from app.db.models.user import User
from app.db.session import get_session_factory
from app.mandates.service import create_mandate
from app.schemas.mandate import MandateIntent, MandatePayload
from app.services.audit_service import get_events_for_user


async def _create_fixture_data():
    """Create an isolated merchant + product + inventory + user for one test."""
    factory = get_session_factory()
    async with factory() as session:
        unique = uuid.uuid4().hex[:8]
        merchant = Merchant(slug=f"mcp-test-{unique}", name="MCP Test Merchant", currency="INR")
        user = User(email=f"mcp-test-{unique}@agentpay.test", name="MCP Test User")
        session.add_all([merchant, user])
        await session.flush()

        product = Product(
            merchant_id=merchant.id,
            sku=f"MCP-SKU-{unique}",
            name="MCP Test Widget",
            description="A widget used only in MCP tests.",
            price_minor=50_000,
            currency="INR",
            category="electronics",
            is_active=True,
        )
        session.add(product)
        await session.flush()
        session.add(Inventory(product_id=product.id, quantity=10, reserved_quantity=0))
        await session.commit()
        return merchant, product, user


async def _create_mandate_for(merchant, user, **overrides: object) -> str:
    defaults: dict[str, object] = {
        "mandate_id": f"M-mcp-{uuid.uuid4().hex[:8]}",
        "merchant_id": str(merchant.id),
        "currency": "INR",
        "max_amount": 500_000,
        "allowed_categories": ["electronics"],
        "allow_addons": False,
        "delivery_requirement": "under_3_days",
        "single_use": True,
        "expires_at": datetime.now(UTC) + timedelta(days=1),
        "intent": MandateIntent(product_type="test widget"),
    }
    defaults.update(overrides)
    payload = MandatePayload(**defaults)  # type: ignore[arg-type]
    factory = get_session_factory()
    async with factory() as session:
        await create_mandate(session, payload, user.id, merchant.id)
        await session.commit()
    return payload.mandate_id


@asynccontextmanager
async def _mcp_client_session():
    """
    Build a throwaway MCPServer, register the real tools onto it, and
    connect a real MCP ClientSession over an in-process ASGI transport (no
    real network port).

    A Streamable HTTP session manager can only be run() once per instance
    (the SDK raises RuntimeError on a second call), and pytest-asyncio gives
    each test its own event loop by default -- so tests cannot share
    app.mcp.server's process-wide singleton the way the real deployed app
    does. Building an independent MCPServer per test (registered with the
    exact same tool functions from app.mcp.tools) sidesteps that entirely
    while still exercising the real tool <-> service wiring.
    """
    from mcp.server.mcpserver import MCPServer
    from mcp.server.streamable_http import TransportSecuritySettings

    from app.mcp.tools import register_tools

    test_server = MCPServer(name="agentpay-test")
    register_tools(test_server)
    # DNS-rebinding host validation is a real-network concern; it has no
    # meaning over an in-process ASGI transport, and its auto-detection
    # doesn't reliably recognize the synthetic "localhost" Host header
    # httpx's ASGITransport sends. Disabling it here is test-only -- this
    # throwaway test_server never touches app.mcp.server's own
    # _mcp_transport_security() (see tests/unit/test_mcp_transport_security.py
    # for that), which explicitly allowlists the deployed hostname and keeps
    # protection enabled in production.
    test_app = test_server.streamable_http_app(
        streamable_http_path="/",
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )

    async with test_server.session_manager.run():
        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=test_app), base_url="http://localhost", follow_redirects=True
        ) as http_client:
            async with streamable_http_client("http://localhost/", http_client=http_client) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    yield session


def _text_of(result) -> str:
    return "\n".join(block.text for block in result.content if hasattr(block, "text"))


def _json_one(text: str) -> dict:
    """Parse a tool result that returns a single JSON object."""
    return json.loads(text)


def _json_many(text: str) -> list[dict]:
    """Parse a tool result that returns a list, rendered as newline-concatenated JSON objects."""
    return json.loads("[" + text.replace("}\n{", "},{") + "]")


async def test_list_tools_exposes_all_eight_commerce_tools() -> None:
    async with _mcp_client_session() as session:
        tools = await session.list_tools()

    tool_names = {t.name for t in tools.tools}
    assert tool_names == {
        "search_products",
        "get_product",
        "create_cart",
        "add_to_cart",
        "request_checkout",
        "complete_purchase",
        "request_authorization",
        "check_authorization_status",
    }


async def test_search_products_returns_catalog() -> None:
    """
    search_products() is scoped to the seeded UrbanNest merchant
    (app.catalog.service.list_products), not every Product row in the
    database -- a throwaway fixture merchant's product is deliberately NOT
    expected to show up here, so this only checks the tool's response
    shape, not fixture-specific content.
    """
    async with _mcp_client_session() as session:
        result = await session.call_tool("search_products", {})

    assert result.is_error is False
    products = _json_many(_text_of(result))
    assert isinstance(products, list)


async def test_get_product_returns_details() -> None:
    _merchant, product, _user = await _create_fixture_data()

    async with _mcp_client_session() as session:
        result = await session.call_tool("get_product", {"product_id": str(product.id)})

    assert result.is_error is False
    data = _json_one(_text_of(result))
    assert data["name"] == "MCP Test Widget"


async def test_get_unknown_product_returns_tool_error() -> None:
    async with _mcp_client_session() as session:
        result = await session.call_tool("get_product", {"product_id": str(uuid.uuid4())})

    assert result.is_error is True
    assert "PRODUCT_NOT_FOUND" in _text_of(result)


async def test_search_products_without_user_id_records_no_activity() -> None:
    """Browsing with no user_id given stays a zero-side-effect read, exactly as before this instrumentation existed."""
    _merchant, _product, user = await _create_fixture_data()

    async with _mcp_client_session() as session:
        await session.call_tool("search_products", {})

    factory = get_session_factory()
    async with factory() as fetch_session:
        events = await get_events_for_user(fetch_session, user.id)
    assert not any(e.event_type == "PRODUCTS_SEARCHED" for e in events)


async def test_search_products_with_user_id_shows_up_in_their_activity() -> None:
    """The live-activity popup's data source: passing user_id makes a search a real, queryable event for that buyer."""
    merchant, _product, user = await _create_fixture_data()

    async with _mcp_client_session() as session:
        result = await session.call_tool("search_products", {"merchant": merchant.slug, "user_id": str(user.id)})
    assert result.is_error is False

    factory = get_session_factory()
    async with factory() as fetch_session:
        events = await get_events_for_user(fetch_session, user.id)
    searched = [e for e in events if e.event_type == "PRODUCTS_SEARCHED"]
    assert len(searched) == 1
    assert searched[0].payload["merchant_name"] == merchant.name
    assert searched[0].user_id == str(user.id)


async def test_get_product_with_user_id_records_product_viewed() -> None:
    _merchant, product, user = await _create_fixture_data()

    async with _mcp_client_session() as session:
        result = await session.call_tool("get_product", {"product_id": str(product.id), "user_id": str(user.id)})
    assert result.is_error is False

    factory = get_session_factory()
    async with factory() as fetch_session:
        events = await get_events_for_user(fetch_session, user.id)
    viewed = [e for e in events if e.event_type == "PRODUCT_VIEWED"]
    assert len(viewed) == 1
    assert viewed[0].payload["product_name"] == "MCP Test Widget"


async def test_full_buyer_flow_through_mcp_with_mocked_razorpay() -> None:
    """
    The exact plan.md Section 1.1 flow, driven through MCP:
    search -> inspect -> create cart -> add product -> request checkout ->
    complete purchase.
    """
    merchant, product, user = await _create_fixture_data()
    mandate_id = await _create_mandate_for(merchant, user)

    with patch("app.payments.checkout.create_order", return_value={"id": f"order_mcp_{uuid.uuid4().hex[:8]}"}):
        async with _mcp_client_session() as session:
            create_result = await session.call_tool(
                "create_cart",
                {"user_id": str(user.id), "merchant_id": str(merchant.id), "currency": "INR"},
            )
            assert create_result.is_error is False
            cart_id = _json_one(_text_of(create_result))["cart_id"]

            add_result = await session.call_tool(
                "add_to_cart", {"cart_id": cart_id, "product_id": str(product.id), "quantity": 1}
            )
            assert add_result.is_error is False
            assert _json_one(_text_of(add_result))["subtotal_minor"] == 50_000

            checkout_result = await session.call_tool(
                "request_checkout", {"cart_id": cart_id, "mandate_id": mandate_id}
            )
            assert checkout_result.is_error is False
            assert _json_one(_text_of(checkout_result))["cart"]["status"] == "FROZEN"

            complete_result = await session.call_tool(
                "complete_purchase", {"cart_id": cart_id, "mandate_id": mandate_id}
            )
            assert complete_result.is_error is False
            session_data = _json_one(_text_of(complete_result))
            assert session_data["razorpay_order_id"].startswith("order_mcp_")
            assert "razorpay_key_id" in session_data


async def test_overspend_attack_is_blocked_through_mcp() -> None:
    """plan.md's canonical demo attack: request an amount over the mandate's cap."""
    merchant, product, user = await _create_fixture_data()
    mandate_id = await _create_mandate_for(merchant, user, max_amount=10_000)  # cap below the 50_000 product

    async with _mcp_client_session() as session:
        create_result = await session.call_tool(
            "create_cart", {"user_id": str(user.id), "merchant_id": str(merchant.id), "currency": "INR"}
        )
        cart_id = _json_one(_text_of(create_result))["cart_id"]

        await session.call_tool("add_to_cart", {"cart_id": cart_id, "product_id": str(product.id), "quantity": 1})

        checkout_result = await session.call_tool("request_checkout", {"cart_id": cart_id, "mandate_id": mandate_id})

    assert checkout_result.is_error is True
    assert "MANDATE_AMOUNT_EXCEEDED" in _text_of(checkout_result)
