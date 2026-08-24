"""
Purpose: Verify app.carts.hashing.compute_cart_hash() is deterministic,
order-independent, and content-sensitive (plan.md Section 10.4).

Pure function tests -- Cart/CartItem are plain ORM objects constructed
in-memory, never persisted, so no database is needed here.
"""
import uuid

from app.carts.hashing import compute_cart_hash
from app.db.models.cart import Cart
from app.db.models.cart_item import CartItem


def _cart(**overrides: object) -> Cart:
    cart = Cart(currency="INR", status="OPEN", subtotal_minor=0)
    cart.id = overrides.get("id", uuid.uuid4())
    return cart


def _item(product_id: uuid.UUID, quantity: int, unit_price_minor: int) -> CartItem:
    return CartItem(
        product_id=product_id,
        quantity=quantity,
        unit_price_minor=unit_price_minor,
        line_total_minor=quantity * unit_price_minor,
    )


def test_hash_is_deterministic() -> None:
    cart = _cart()
    product_id = uuid.uuid4()
    items = [_item(product_id, 2, 1000)]

    first = compute_cart_hash(cart, items)
    second = compute_cart_hash(cart, items)

    assert first == second


def test_hash_is_independent_of_item_order() -> None:
    cart = _cart()
    product_a, product_b = uuid.uuid4(), uuid.uuid4()
    items_ab = [_item(product_a, 1, 1000), _item(product_b, 2, 500)]
    items_ba = [_item(product_b, 2, 500), _item(product_a, 1, 1000)]

    assert compute_cart_hash(cart, items_ab) == compute_cart_hash(cart, items_ba)


def test_hash_changes_when_quantity_changes() -> None:
    cart = _cart()
    product_id = uuid.uuid4()

    original = compute_cart_hash(cart, [_item(product_id, 1, 1000)])
    modified = compute_cart_hash(cart, [_item(product_id, 2, 1000)])

    assert original != modified


def test_hash_changes_when_an_item_is_added() -> None:
    cart = _cart()
    product_a, product_b = uuid.uuid4(), uuid.uuid4()

    before = compute_cart_hash(cart, [_item(product_a, 1, 1000)])
    after = compute_cart_hash(cart, [_item(product_a, 1, 1000), _item(product_b, 1, 500)])

    assert before != after


def test_hash_differs_between_different_carts_with_same_items() -> None:
    """Two distinct carts with identical items must not collide -- cart_id is part of the hash."""
    product_id = uuid.uuid4()
    items = [_item(product_id, 1, 1000)]

    hash_a = compute_cart_hash(_cart(), items)
    hash_b = compute_cart_hash(_cart(), items)

    assert hash_a != hash_b
