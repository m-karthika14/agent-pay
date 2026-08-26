"""
Purpose: Mutable shopping cart lifecycle (plan.md Section 10.1-10.3).

Responsibilities:
- create_cart(): open a new cart for a user/merchant.
- add_cart_item() / update_cart_item_quantity() / remove_cart_item(): mutate
  an OPEN cart's line items, always keeping subtotal_minor consistent.
- get_cart(): read a cart with its items.

Mutation is only allowed while cart.status == OPEN (plan.md Section 10.3).
Freezing an OPEN cart into an immutable, hashed FROZEN cart is Phase 3's
responsibility (app.carts.freeze) — this module never sets frozen_at/
frozen_hash itself.
"""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import CART_STATUS_OPEN
from app.db.models.cart import Cart
from app.db.models.cart_item import CartItem
from app.db.models.inventory import Inventory
from app.db.models.mandate import Mandate
from app.db.models.merchant import Merchant
from app.db.models.product import Product
from app.db.models.user import User
from app.schemas.cart import CartItemResponse, CartResponse
from app.schemas.common import NotFoundError, ValidationError


async def to_cart_response(session: AsyncSession, cart: Cart) -> CartResponse:
    """
    Build the API-facing CartResponse for a cart, including its items.

    Public (not underscore-prefixed) because app.services.checkout_service
    reuses this exact function rather than re-deriving the same response
    shape (plan.md rule: reuse existing code instead of duplicating logic).
    """
    result = await session.execute(
        select(CartItem, Product.name)
        .join(Product, Product.id == CartItem.product_id)
        .where(CartItem.cart_id == cart.id)
        .order_by(CartItem.id)
    )
    items = [
        CartItemResponse(
            item_id=str(item.id),
            product_id=str(item.product_id),
            product_name=product_name,
            quantity=item.quantity,
            unit_price_minor=item.unit_price_minor,
            line_total_minor=item.line_total_minor,
        )
        for item, product_name in result.all()
    ]

    business_mandate_id = None
    if cart.mandate_id is not None:
        # Lets a client that lost its own state (e.g. a page refresh
        # mid-checkout) recover which mandate this cart is frozen under,
        # rather than only being able to detect "already frozen" with no
        # way to continue -- see frontend/src/pages/CheckoutPage.tsx.
        mandate_row = await session.get(Mandate, cart.mandate_id)
        business_mandate_id = mandate_row.mandate_id if mandate_row else None

    return CartResponse(
        cart_id=str(cart.id),
        user_id=str(cart.user_id),
        merchant_id=str(cart.merchant_id),
        status=cart.status,
        currency=cart.currency,
        subtotal_minor=cart.subtotal_minor,
        frozen_at=cart.frozen_at,
        frozen_hash=cart.frozen_hash,
        mandate_id=business_mandate_id,
        items=items,
    )


async def _get_open_cart_or_raise(session: AsyncSession, cart_id: uuid.UUID) -> Cart:
    """Fetch a cart and verify it exists and is still OPEN (mutable)."""
    cart = await session.get(Cart, cart_id)
    if cart is None:
        raise NotFoundError("CART_NOT_FOUND", f"No cart with id '{cart_id}'.")
    if cart.status != CART_STATUS_OPEN:
        raise ValidationError(
            "CART_NOT_OPEN", f"Cart '{cart_id}' is '{cart.status}' and can no longer be modified."
        )
    return cart


async def _recalculate_subtotal(session: AsyncSession, cart: Cart) -> None:
    """Recompute cart.subtotal_minor from its current line items."""
    result = await session.execute(
        select(CartItem.line_total_minor).where(CartItem.cart_id == cart.id)
    )
    cart.subtotal_minor = sum(result.scalars().all())
    await session.flush()


async def create_cart(
    session: AsyncSession, user_id: uuid.UUID, merchant_id: uuid.UUID, currency: str
) -> CartResponse:
    """
    Create a new, empty, OPEN cart for a user at a merchant.

    Args:
        session: Active AsyncSession.
        user_id: The user the cart belongs to.
        merchant_id: The merchant the cart is for.
        currency: ISO 4217 currency code for the cart.

    Returns:
        The newly created (empty) cart.

    Raises:
        NotFoundError: If the user or merchant does not exist.
    """
    if await session.get(User, user_id) is None:
        raise NotFoundError("USER_NOT_FOUND", f"No user with id '{user_id}'.")
    if await session.get(Merchant, merchant_id) is None:
        raise NotFoundError("MERCHANT_NOT_FOUND", f"No merchant with id '{merchant_id}'.")

    cart = Cart(
        user_id=user_id,
        merchant_id=merchant_id,
        status=CART_STATUS_OPEN,
        currency=currency,
        subtotal_minor=0,
    )
    session.add(cart)
    await session.flush()
    return await to_cart_response(session, cart)


async def get_cart(session: AsyncSession, cart_id: uuid.UUID) -> CartResponse:
    """
    Fetch a cart with its current line items.

    Args:
        session: Active AsyncSession.
        cart_id: The cart to fetch.

    Returns:
        The cart and its items.

    Raises:
        NotFoundError: If no cart exists with that id.
    """
    cart = await session.get(Cart, cart_id)
    if cart is None:
        raise NotFoundError("CART_NOT_FOUND", f"No cart with id '{cart_id}'.")
    return await to_cart_response(session, cart)


async def get_cart_by_mandate(session: AsyncSession, mandate_row_id: uuid.UUID) -> CartResponse | None:
    """
    Fetch the cart currently linked to a mandate, if any (plan.md Section
    10.4-adjacent, added Phase 10: Cart.mandate_id is set once
    checkout_service.request_checkout() freezes a cart under this mandate).

    Returns None (rather than raising) before any checkout has been
    requested yet -- a mandate legitimately has no linked cart between its
    creation and a buyer agent's first request_checkout() call, so this is
    a normal state for a live "watch this purchase happen" panel to poll,
    not an error.

    Args:
        session: Active AsyncSession.
        mandate_row_id: The mandate's internal UUID (Mandate.id, not its
            business-facing mandate_id string).

    Returns:
        The linked cart, or None if no cart has been frozen under this
        mandate yet.
    """
    result = await session.execute(select(Cart).where(Cart.mandate_id == mandate_row_id))
    cart = result.scalar_one_or_none()
    if cart is None:
        return None
    return await to_cart_response(session, cart)


async def get_open_cart_for_user(
    session: AsyncSession, user_id: uuid.UUID, merchant_id: uuid.UUID | None = None
) -> CartResponse | None:
    """
    Fetch a user's current OPEN cart, if any -- the most recently created
    one, in the unlikely event more than one somehow exists.

    Lets the storefront discover a cart Claude created via MCP under this
    same user_id (plan.md Section 19 login): a fresh browser session has no
    cart_id of its own stored locally, so without this lookup it would
    never find a cart it didn't create itself.

    Args:
        session: Active AsyncSession.
        user_id: The buyer's internal User.id.
        merchant_id: If given, only consider carts at that merchant. With
            more than one merchant, a user can have a separate OPEN cart at
            each -- omitting this returns whichever is most recent across
            all of them, which is what a merchant-agnostic caller (e.g. the
            "Buying History"-style views) wants; a merchant-scoped
            storefront page should always pass this so its own cart page
            never shows a different merchant's cart.

    Returns:
        The cart, or None if this user has no matching OPEN cart right now
        -- a normal state (nothing added yet, or their last cart already
        froze), not an error.
    """
    query = select(Cart).where(Cart.user_id == user_id, Cart.status == CART_STATUS_OPEN)
    if merchant_id is not None:
        query = query.where(Cart.merchant_id == merchant_id)
    result = await session.execute(query.order_by(Cart.created_at.desc()).limit(1))
    cart = result.scalars().first()
    if cart is None:
        return None
    return await to_cart_response(session, cart)


async def _add_or_merge_item(session: AsyncSession, cart: Cart, product: Product, quantity: int) -> None:
    """
    Insert a new line item for `product`/`quantity`, or merge into an
    existing line for the same product, then recalculate cart.subtotal_minor.

    Shared by add_cart_item() (buyer-facing, OPEN carts only) and
    merge_item_into_cart() (system-facing, applied to an already-FROZEN cart
    by app.services.checkout_service after Intent Gate approval) -- the
    merge/recalculate mechanics are identical either way; only the caller
    decides whether cart.status permits the mutation (plan.md rule: reuse
    existing code instead of duplicating logic).

    Raises:
        ValidationError: If `quantity` would exceed available inventory.
    """
    existing_result = await session.execute(
        select(CartItem).where(CartItem.cart_id == cart.id, CartItem.product_id == product.id)
    )
    existing_item = existing_result.scalar_one_or_none()
    requested_total_quantity = quantity + (existing_item.quantity if existing_item else 0)

    inventory_result = await session.execute(select(Inventory).where(Inventory.product_id == product.id))
    inventory = inventory_result.scalar_one_or_none()
    available = (inventory.quantity - inventory.reserved_quantity) if inventory else 0
    if requested_total_quantity > available:
        raise ValidationError(
            "INSUFFICIENT_INVENTORY",
            f"Only {available} unit(s) of '{product.name}' are available.",
        )

    if existing_item is not None:
        existing_item.quantity = requested_total_quantity
        existing_item.line_total_minor = existing_item.quantity * existing_item.unit_price_minor
    else:
        session.add(
            CartItem(
                cart_id=cart.id,
                product_id=product.id,
                quantity=quantity,
                unit_price_minor=product.price_minor,
                line_total_minor=quantity * product.price_minor,
            )
        )
    await session.flush()
    await _recalculate_subtotal(session, cart)


async def add_cart_item(
    session: AsyncSession, cart_id: uuid.UUID, product_id: uuid.UUID, quantity: int
) -> CartResponse:
    """
    Add a product to an OPEN cart, merging into an existing line if the
    product is already present.

    Per plan.md Section 10.2: verifies the product exists and is active,
    reads its current price (captured onto the line item so a later catalog
    price change cannot silently alter this cart), checks inventory, then
    recalculates the cart subtotal.

    Args:
        session: Active AsyncSession.
        cart_id: The cart to add to.
        product_id: The product being added.
        quantity: How many units to add.

    Returns:
        The updated cart.

    Raises:
        NotFoundError: If the cart or product does not exist.
        ValidationError: If the cart is not OPEN, the product is inactive,
            or there isn't enough available inventory.
    """
    cart = await _get_open_cart_or_raise(session, cart_id)

    product = await session.get(Product, product_id)
    if product is None or not product.is_active:
        raise NotFoundError("PRODUCT_NOT_FOUND", f"No active product with id '{product_id}'.")

    await _add_or_merge_item(session, cart, product, quantity)
    return await to_cart_response(session, cart)


async def merge_item_into_cart(session: AsyncSession, cart: Cart, product: Product, quantity: int) -> None:
    """
    Apply an Intent-Gate-approved merchant proposal to an already-FROZEN
    cart (plan.md Section 15 step 12).

    This deliberately bypasses add_cart_item()'s OPEN-status guard: the
    caller (app.services.checkout_service) is AgentPay's own deterministic
    backend code applying a change AgentPay itself decided to allow, not a
    buyer mutating their cart directly (plan.md Rule 6 -- the merchant agent
    can never execute this itself; only AgentPay can, and only after both
    the deterministic proposal pathway and the Intent Gate approved it).

    Args:
        session: Active AsyncSession.
        cart: The FROZEN cart to modify. The caller must re-freeze it (via
            app.carts.freeze.freeze_cart) immediately after this returns --
            this function does not touch frozen_hash/frozen_at itself, so
            the cart is briefly in an inconsistent (FROZEN but unhashed-for-
            its-new-contents) state until the caller re-freezes it.
        product: The proposed product to add.
        quantity: How many units to add.

    Raises:
        ValidationError: If `quantity` would exceed available inventory.
    """
    await _add_or_merge_item(session, cart, product, quantity)


async def update_cart_item_quantity(
    session: AsyncSession, cart_id: uuid.UUID, item_id: uuid.UUID, quantity: int
) -> CartResponse:
    """
    Change a line item's quantity in an OPEN cart.

    Args:
        session: Active AsyncSession.
        cart_id: The cart containing the item.
        item_id: The line item to update.
        quantity: The new quantity (must be > 0; use remove_cart_item to
            delete a line entirely).

    Returns:
        The updated cart.

    Raises:
        NotFoundError: If the cart or item does not exist.
        ValidationError: If the cart is not OPEN or inventory is insufficient.
    """
    cart = await _get_open_cart_or_raise(session, cart_id)

    item = await session.get(CartItem, item_id)
    if item is None or item.cart_id != cart.id:
        raise NotFoundError("CART_ITEM_NOT_FOUND", f"No item '{item_id}' in cart '{cart_id}'.")

    inventory_result = await session.execute(
        select(Inventory).where(Inventory.product_id == item.product_id)
    )
    inventory = inventory_result.scalar_one_or_none()
    available = (inventory.quantity - inventory.reserved_quantity) if inventory else 0
    if quantity > available:
        raise ValidationError(
            "INSUFFICIENT_INVENTORY", f"Only {available} unit(s) of this product are available."
        )

    item.quantity = quantity
    item.line_total_minor = quantity * item.unit_price_minor
    await session.flush()
    await _recalculate_subtotal(session, cart)
    return await to_cart_response(session, cart)


async def remove_cart_item(session: AsyncSession, cart_id: uuid.UUID, item_id: uuid.UUID) -> CartResponse:
    """
    Remove a line item from an OPEN cart.

    Args:
        session: Active AsyncSession.
        cart_id: The cart containing the item.
        item_id: The line item to remove.

    Returns:
        The updated cart.

    Raises:
        NotFoundError: If the cart or item does not exist.
        ValidationError: If the cart is not OPEN.
    """
    cart = await _get_open_cart_or_raise(session, cart_id)

    item = await session.get(CartItem, item_id)
    if item is None or item.cart_id != cart.id:
        raise NotFoundError("CART_ITEM_NOT_FOUND", f"No item '{item_id}' in cart '{cart_id}'.")

    await session.delete(item)
    await session.flush()
    await _recalculate_subtotal(session, cart)
    return await to_cart_response(session, cart)
