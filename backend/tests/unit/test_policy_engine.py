"""
Purpose: Verify app.policy.checks.check_mandate() correctly delegates to
app.security.mandate_verifier.verify_mandate() using the cart's own
merchant/amount/currency as the "requested" values (plan.md Section 11.1).

Pure function tests -- Cart is a plain in-memory ORM object; Mandate row
status is passed directly rather than persisted.
"""
import uuid
from datetime import UTC, datetime, timedelta

from app.db.models.cart import Cart
from app.db.models.mandate import Mandate
from app.policy import reason_codes
from app.policy.checks import check_mandate
from app.schemas.mandate import MandateIntent, MandatePayload, MandateStatus, SignedMandate
from app.security.canonical import canonicalize_mandate
from app.security.signing import encode_key, generate_ed25519_keypair, sign_bytes
import base64


def _signed_mandate(private_key, merchant_id: str, **overrides: object) -> SignedMandate:
    defaults: dict[str, object] = {
        "mandate_id": "M-001",
        "merchant_id": merchant_id,
        "currency": "INR",
        "max_amount": 300_000,
        "allowed_categories": ["electronics"],
        "allow_addons": False,
        "delivery_requirement": "under_3_days",
        "single_use": True,
        "expires_at": datetime.now(UTC) + timedelta(days=1),
        "intent": MandateIntent(product_type="wireless earbuds"),
    }
    defaults.update(overrides)
    payload = MandatePayload(**defaults)  # type: ignore[arg-type]
    signature = sign_bytes(canonicalize_mandate(payload), private_key)
    return SignedMandate(payload=payload, signature=base64.b64encode(signature).decode("ascii"))


def _mandate_row(status: MandateStatus = MandateStatus.ACTIVE) -> Mandate:
    row = Mandate(status=status, single_use=True, expires_at=datetime.now(UTC) + timedelta(days=1))
    row.id = uuid.uuid4()
    return row


def _cart(merchant_id: uuid.UUID, subtotal_minor: int, currency: str = "INR") -> Cart:
    cart = Cart(merchant_id=merchant_id, currency=currency, subtotal_minor=subtotal_minor, status="OPEN")
    cart.id = uuid.uuid4()
    return cart


def test_valid_mandate_and_cart_passes() -> None:
    private_key, public_key = generate_ed25519_keypair()
    merchant_id = uuid.uuid4()
    mandate = _signed_mandate(private_key, str(merchant_id))
    cart = _cart(merchant_id, subtotal_minor=250_000)

    result = check_mandate(mandate, _mandate_row(), encode_key(public_key), cart)

    assert result.passed is True


def test_cart_amount_exceeding_mandate_cap_is_blocked() -> None:
    private_key, public_key = generate_ed25519_keypair()
    merchant_id = uuid.uuid4()
    mandate = _signed_mandate(private_key, str(merchant_id), max_amount=300_000)
    cart = _cart(merchant_id, subtotal_minor=599_900)

    result = check_mandate(mandate, _mandate_row(), encode_key(public_key), cart)

    assert result.passed is False
    assert result.reason_code == reason_codes.MANDATE_AMOUNT_EXCEEDED


def test_cart_for_wrong_merchant_is_blocked() -> None:
    private_key, public_key = generate_ed25519_keypair()
    mandate_merchant_id = uuid.uuid4()
    cart_merchant_id = uuid.uuid4()
    mandate = _signed_mandate(private_key, str(mandate_merchant_id))
    cart = _cart(cart_merchant_id, subtotal_minor=100_000)

    result = check_mandate(mandate, _mandate_row(), encode_key(public_key), cart)

    assert result.passed is False
    assert result.reason_code == reason_codes.MANDATE_MERCHANT_MISMATCH


def test_consumed_mandate_is_blocked_as_replay() -> None:
    private_key, public_key = generate_ed25519_keypair()
    merchant_id = uuid.uuid4()
    mandate = _signed_mandate(private_key, str(merchant_id))
    cart = _cart(merchant_id, subtotal_minor=100_000)

    result = check_mandate(mandate, _mandate_row(status=MandateStatus.CONSUMED), encode_key(public_key), cart)

    assert result.passed is False
    assert result.reason_code == reason_codes.REPLAY_DETECTED


def test_currency_mismatch_is_blocked() -> None:
    private_key, public_key = generate_ed25519_keypair()
    merchant_id = uuid.uuid4()
    mandate = _signed_mandate(private_key, str(merchant_id), currency="INR")
    cart = _cart(merchant_id, subtotal_minor=100_000, currency="USD")

    result = check_mandate(mandate, _mandate_row(), encode_key(public_key), cart)

    assert result.passed is False
    assert result.reason_code == reason_codes.MANDATE_CURRENCY_MISMATCH
