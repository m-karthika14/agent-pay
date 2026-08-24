"""
Purpose: Verify app.policy.checks.check_idempotency() (plan.md Section 11.1 /
Phase 3 acceptance: "duplicate request fails").

Pure function test -- Cart is a plain ORM object constructed in-memory.
"""
import uuid

from app.db.models.cart import Cart
from app.policy import reason_codes
from app.policy.checks import check_idempotency


def test_duplicate_request_on_frozen_cart_is_rejected() -> None:
    cart = Cart(currency="INR", status="FROZEN", subtotal_minor=100_000, frozen_hash="abc123")
    cart.id = uuid.uuid4()

    result = check_idempotency(cart, current_hash="abc123")

    assert result.passed is False
    assert result.reason_code == reason_codes.IDEMPOTENCY_DUPLICATE
    assert str(cart.id) in result.reason or "abc123" in result.reason
