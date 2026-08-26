"""
Purpose: The six MCP commerce tools Claude (the external buyer agent) uses
to transact with AgentPay's demo merchants -- UrbanNest and TechHub
(plan.md Section 17).

Every tool here is a thin wrapper: it opens a database session and calls
the exact same service function the REST API routes call
(app.catalog.service, app.carts.service, app.services.checkout_service,
app.payments.checkout) -- never its own reimplementation. This is the rule
stated directly in plan.md Section 17: "MCP tools should not reimplement
business logic... There must be one source of truth." That's also why this
module never touches app.policy directly -- all authorization logic lives
inside the services these tools call, so REST and MCP can never drift into
two different policy engines.

Docstrings here double as each tool's description shown to the calling LLM
client (per the MCP protocol), so they are written to explain to Claude
*when* and *how* to call each tool, not just what the Python does.

Tools are defined as plain functions and attached to a server via
register_tools() rather than a module-level `@mcp.tool()` decorator, so a
fresh, independent MCPServer instance can be built on demand -- production
code builds exactly one (app.mcp.server), while tests build a throwaway one
per test (a Streamable HTTP session manager can only be run() once per
instance, so tests cannot share the production singleton).
"""
import uuid

from mcp.server.mcpserver import MCPServer

from app.carts import service as carts_service
from app.catalog import service as catalog_service
from app.mcp.context import mcp_db_session
from app.merchants.service import get_merchant_by_slug
from app.payments.checkout import create_checkout_session
from app.schemas.cart import CartResponse
from app.schemas.checkout import CheckoutResponse
from app.schemas.common import NotFoundError
from app.schemas.payment import CheckoutSessionResponse
from app.schemas.product import ProductResponse
from app.services import checkout_service


async def search_products(merchant: str | None = None) -> list[ProductResponse]:
    """
    List active products across AgentPay's demo merchants (currently
    UrbanNest and TechHub) -- or just one, if you already know which.

    Call this first to discover what's available before creating a cart. If
    the buyer's request could be satisfied by more than one merchant (e.g.
    both sell wireless earbuds), leave `merchant` unset so you see every
    merchant's offering together and can compare price/category before
    choosing -- do not assume one merchant is better without checking. Each
    result includes the product's id, name, description, price (in minor
    currency units, e.g. paise for INR), currency, category, which merchant
    it belongs to (merchant_name/merchant_slug), live stock availability,
    delivery policy, and return policy.

    Args:
        merchant: Optional merchant slug (e.g. "techhub") to search only
            that merchant. Omit to search every demo merchant at once.
    """
    async with mcp_db_session() as session:
        merchant_id = None
        if merchant is not None:
            merchant_row = await get_merchant_by_slug(session, merchant)
            if merchant_row is None:
                raise NotFoundError("MERCHANT_NOT_FOUND", f"No merchant with slug '{merchant}'.")
            merchant_id = merchant_row.id
        return await catalog_service.list_products(session, merchant_id)


async def get_product(product_id: str) -> ProductResponse:
    """
    Fetch full details for a single product by its id.

    Args:
        product_id: A product id, as returned by search_products().
    """
    async with mcp_db_session() as session:
        return await catalog_service.get_product(session, uuid.UUID(product_id))


async def create_cart(user_id: str, merchant_id: str, currency: str = "INR") -> CartResponse:
    """
    Create a new, empty cart for a user at a merchant.

    Call this once you know which product(s) you want to buy, before
    add_to_cart(). The cart starts empty and mutable (status OPEN).

    Args:
        user_id: The buyer's user id.
        merchant_id: The merchant to shop at (from a product's merchant_id
            field, returned by search_products()/get_product()).
        currency: ISO 4217 currency code for the cart. Defaults to "INR".
    """
    async with mcp_db_session() as session:
        return await carts_service.create_cart(
            session, uuid.UUID(user_id), uuid.UUID(merchant_id), currency
        )


async def add_to_cart(cart_id: str, product_id: str, quantity: int) -> CartResponse:
    """
    Add a product to an existing, still-open cart.

    Adding a product that's already in the cart increases its quantity
    rather than creating a duplicate line. Fails if the requested quantity
    exceeds available stock, or if the cart has already been frozen by a
    prior request_checkout() call.

    Args:
        cart_id: The cart to add to, from create_cart().
        product_id: The product to add.
        quantity: How many units to add (must be a positive integer).
    """
    async with mcp_db_session() as session:
        return await carts_service.add_cart_item(session, uuid.UUID(cart_id), uuid.UUID(product_id), quantity)


async def request_checkout(cart_id: str, mandate_id: str) -> CheckoutResponse:
    """
    Run AgentPay's deterministic authorization checks against the cart and,
    if they all pass, freeze it so it can be purchased.

    Call this once the cart contains everything you intend to buy. This can
    fail -- and SHOULD be treated as a hard stop, not retried with a
    workaround -- if the cart's total exceeds the mandate's authorized
    spending cap, the cart contains a product category the mandate doesn't
    allow, the mandate has expired or was already used for a purchase, or a
    product's price/stock changed since it was added to the cart. The error
    message names the specific reason.

    Args:
        cart_id: The cart to check out.
        mandate_id: The signed mandate id authorizing this purchase (the
            user's spending/intent authorization -- not something you choose).
    """
    async with mcp_db_session() as session:
        return await checkout_service.request_checkout(session, uuid.UUID(cart_id), mandate_id)


async def complete_purchase(cart_id: str, mandate_id: str) -> CheckoutSessionResponse:
    """
    Create the Razorpay Test Mode order for a cart that has already passed
    request_checkout(), returning what's needed to pay for it.

    Important: calling this does not itself move money, and you never
    handle card/UPI credentials. A human completes the actual Razorpay Test
    Mode Checkout using the returned order id and key; AgentPay confirms
    the payment asynchronously once Razorpay's webhook reports it captured.

    Args:
        cart_id: The cart to complete. Must already be frozen -- call
            request_checkout() first if you haven't.
        mandate_id: The signed mandate id authorizing this purchase.
    """
    async with mcp_db_session() as session:
        return await create_checkout_session(session, uuid.UUID(cart_id), mandate_id)


#: Every tool function, in the order plan.md Section 17 lists them.
ALL_TOOLS = (search_products, get_product, create_cart, add_to_cart, request_checkout, complete_purchase)


def register_tools(server: MCPServer) -> None:
    """
    Attach all six commerce tools to an MCPServer instance.

    Args:
        server: The MCPServer to register tools onto. Production code
            (app.mcp.server) calls this once for the process-wide server;
            tests call it against their own throwaway instance.
    """
    for tool_fn in ALL_TOOLS:
        server.add_tool(tool_fn)
