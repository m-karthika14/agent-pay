"""
Purpose: Canonical cart representation and SHA-256 hashing (plan.md Section 10.4).

Responsibilities:
- Produce the exact same hash for the exact same logical cart contents,
  regardless of the order items were added or fetched from the database.
- Be the single function both freeze_cart() (Phase 3) and any future
  re-validation logic (Phase 8) call, so a frozen cart's hash is always
  checked against the same canonical representation it was created from.

This module is pure/side-effect-free, mirroring app.security.canonical for
mandates. It never touches the database or calls freeze_cart() itself.
"""
import hashlib
import json

from app.db.models.cart import Cart
from app.db.models.cart_item import CartItem


def compute_cart_hash(cart: Cart, items: list[CartItem]) -> str:
    """
    Compute the SHA-256 hex digest of a cart's canonical contents.

    Args:
        cart: The cart being hashed (currency and id are part of the hash so
            a hash can never accidentally match a different cart/currency).
        items: The cart's line items. Order does not matter -- items are
            sorted by product_id before hashing (plan.md Section 10.4 step 2:
            "normalize item order").

    Returns:
        Lowercase hex-encoded SHA-256 digest over the cart id, currency, and
        each item's product id / quantity / unit price / line total.
    """
    normalized_items = sorted(
        (
            {
                "product_id": str(item.product_id),
                "quantity": item.quantity,
                "unit_price_minor": item.unit_price_minor,
                "line_total_minor": item.line_total_minor,
            }
            for item in items
        ),
        key=lambda entry: entry["product_id"],
    )
    normalized = {
        "cart_id": str(cart.id),
        "currency": cart.currency,
        "items": normalized_items,
    }
    canonical_json = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
