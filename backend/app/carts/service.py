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
from app.db.models.merchant import Merchant
from app.db.models.product import Product
from app.db.models.user import User
from app.schemas.cart import CartItemResponse, CartResponse
from app.schemas.common import NotFoundError, ValidationError


async def _to_cart_response(session: AsyncSession, cart: Cart) -> CartResponse:
    """Build the API-facing CartResponse for a cart, including its items."""
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
    return CartResponse(
        cart_id=str(cart.id),
        user_id=str(cart.user_id),
        merchant_id=str(cart.merchant_id),
        status=cart.status,
        currency=cart.currency,
        subtotal_minor=cart.subtotal_minor,
        frozen_at=cart.frozen_at,
        frozen_hash=cart.frozen_hash,
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
    return await _to_cart_response(session, cart)


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
    return await _to_cart_response(session, cart)


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

    existing_result = await session.execute(
        select(CartItem).where(CartItem.cart_id == cart_id, CartItem.product_id == product_id)
    )
    existing_item = existing_result.scalar_one_or_none()
    requested_total_quantity = quantity + (existing_item.quantity if existing_item else 0)

    inventory_result = await session.execute(
        select(Inventory).where(Inventory.product_id == product_id)
    )
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
                cart_id=cart_id,
                product_id=product_id,
                quantity=quantity,
                unit_price_minor=product.price_minor,
                line_total_minor=quantity * product.price_minor,
            )
        )
    await session.flush()
    await _recalculate_subtotal(session, cart)
    return await _to_cart_response(session, cart)


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
    return await _to_cart_response(session, cart)


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
    return await _to_cart_response(session, cart)
