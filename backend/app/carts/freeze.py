"""
Purpose: Freeze a cart into an immutable, hashed state (plan.md Section 10.4).

Responsibilities:
- freeze_cart(): compute and persist a cart's frozen_hash, set frozen_at,
  and transition status OPEN -> FROZEN. Once frozen, app.carts.service's
  mutation functions refuse further changes (they check status == OPEN).
- verify_cart_integrity(): recompute a cart's hash from its CURRENT items
  and compare it to the stored frozen_hash, detecting any post-freeze
  tampering (plan.md Rule: "frozen hash != final hash -> BLOCK").

This module never decides whether a cart is ALLOWED to be frozen (mandate
checks, category checks, etc.) -- that is app.policy's job. This module only
performs/verifies the freeze operation itself.
"""
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.carts.hashing import compute_cart_hash
from app.core.constants import CART_STATUS_FROZEN
from app.db.models.cart import Cart
from app.db.models.cart_item import CartItem


async def _load_items(session: AsyncSession, cart_id) -> list[CartItem]:
    """Fetch a cart's current line items."""
    result = await session.execute(select(CartItem).where(CartItem.cart_id == cart_id))
    return list(result.scalars().all())


async def freeze_cart(session: AsyncSession, cart: Cart) -> Cart:
    """
    Freeze an OPEN cart: compute its hash and transition it to FROZEN.

    Args:
        session: Active AsyncSession.
        cart: The cart to freeze. Must currently be OPEN -- callers
            (app.services.checkout_service) are responsible for only
            calling this once hard checks have passed.

    Returns:
        The same Cart row, now with frozen_hash, frozen_at, and
        status=FROZEN set and persisted.
    """
    items = await _load_items(session, cart.id)
    cart.frozen_hash = compute_cart_hash(cart, items)
    cart.frozen_at = datetime.now(UTC)
    cart.status = CART_STATUS_FROZEN
    await session.flush()
    return cart


async def verify_cart_integrity(session: AsyncSession, cart: Cart) -> bool:
    """
    Check whether a FROZEN cart's current contents still match its stored
    frozen_hash.

    Args:
        session: Active AsyncSession.
        cart: A cart that has already been frozen (cart.frozen_hash is set).

    Returns:
        True if the recomputed hash matches the stored frozen_hash (cart is
        untampered), False otherwise. Returns False (fail closed) if the
        cart has no frozen_hash at all, since integrity cannot be verified
        against nothing.
    """
    if cart.frozen_hash is None:
        return False
    items = await _load_items(session, cart.id)
    return compute_cart_hash(cart, items) == cart.frozen_hash
