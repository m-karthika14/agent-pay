"""
Purpose: Verify app.security.mandate_verifier.verify_mandate() against the
Phase 1 end-of-day acceptance criteria from plan.md/final.md:

    Valid mandate     -> PASS
    Tampered mandate  -> REJECT
    Expired mandate   -> REJECT
    Replay            -> REJECT

Plus the additional deterministic checks described in plan.md Section 9.4
(merchant, amount, category, currency mismatch).
"""
from datetime import UTC, datetime, timedelta

from app.policy import reason_codes
from app.schemas.mandate import MandateIntent, MandatePayload, MandateStatus, SignedMandate
from app.security.canonical import canonicalize_mandate
from app.security.mandate_verifier import verify_mandate
from app.security.signing import encode_key, generate_ed25519_keypair, sign_bytes
import base64


def _signed_mandate(private_key, **overrides: object) -> SignedMandate:
    defaults: dict[str, object] = {
        "mandate_id": "M-001",
        "merchant_id": "urbannest",
        "currency": "INR",
        "max_amount": 300000,
        "allowed_categories": ["electronics"],
        "allow_addons": False,
        "delivery_requirement": "under_3_days",
        "single_use": True,
        "expires_at": datetime.now(UTC) + timedelta(days=1),
        "intent": MandateIntent(product_type="wireless earbuds", notes="no accessories"),
    }
    defaults.update(overrides)
    payload = MandatePayload(**defaults)  # type: ignore[arg-type]
    signature = sign_bytes(canonicalize_mandate(payload), private_key)
    return SignedMandate(payload=payload, signature=base64.b64encode(signature).decode("ascii"))


def test_valid_mandate_passes() -> None:
    private_key, public_key = generate_ed25519_keypair()
    mandate = _signed_mandate(private_key)

    result = verify_mandate(
        mandate, encode_key(public_key), current_status=MandateStatus.ACTIVE
    )

    assert result.valid is True
    assert result.reason_code is None


def test_tampered_mandate_is_rejected() -> None:
    """A mandate whose payload was altered after signing must fail signature verification."""
    private_key, public_key = generate_ed25519_keypair()
    mandate = _signed_mandate(private_key, max_amount=300000)

    # Simulate tampering: bump the authorized amount after the signature was produced.
    tampered_payload = mandate.payload.model_copy(update={"max_amount": 999900})
    tampered_mandate = SignedMandate(payload=tampered_payload, signature=mandate.signature)

    result = verify_mandate(
        tampered_mandate, encode_key(public_key), current_status=MandateStatus.ACTIVE
    )

    assert result.valid is False
    assert result.reason_code == reason_codes.MANDATE_INVALID_SIGNATURE


def test_expired_mandate_is_rejected() -> None:
    private_key, public_key = generate_ed25519_keypair()
    mandate = _signed_mandate(private_key, expires_at=datetime.now(UTC) - timedelta(days=1))

    result = verify_mandate(
        mandate, encode_key(public_key), current_status=MandateStatus.ACTIVE
    )

    assert result.valid is False
    assert result.reason_code == reason_codes.MANDATE_EXPIRED


def test_replayed_single_use_mandate_is_rejected() -> None:
    """A single-use mandate that has already been consumed must be rejected as a replay."""
    private_key, public_key = generate_ed25519_keypair()
    mandate = _signed_mandate(private_key, single_use=True)

    result = verify_mandate(
        mandate, encode_key(public_key), current_status=MandateStatus.CONSUMED
    )

    assert result.valid is False
    assert result.reason_code == reason_codes.REPLAY_DETECTED


def test_wrong_merchant_is_rejected() -> None:
    private_key, public_key = generate_ed25519_keypair()
    mandate = _signed_mandate(private_key, merchant_id="urbannest")

    result = verify_mandate(
        mandate,
        encode_key(public_key),
        current_status=MandateStatus.ACTIVE,
        expected_merchant_id="some-other-merchant",
    )

    assert result.valid is False
    assert result.reason_code == reason_codes.MANDATE_MERCHANT_MISMATCH


def test_amount_exceeding_cap_is_rejected() -> None:
    private_key, public_key = generate_ed25519_keypair()
    mandate = _signed_mandate(private_key, max_amount=300000)

    result = verify_mandate(
        mandate,
        encode_key(public_key),
        current_status=MandateStatus.ACTIVE,
        requested_amount=599900,
    )

    assert result.valid is False
    assert result.reason_code == reason_codes.MANDATE_AMOUNT_EXCEEDED


def test_disallowed_category_is_rejected() -> None:
    private_key, public_key = generate_ed25519_keypair()
    mandate = _signed_mandate(private_key, allowed_categories=["electronics"])

    result = verify_mandate(
        mandate,
        encode_key(public_key),
        current_status=MandateStatus.ACTIVE,
        requested_category="fashion",
    )

    assert result.valid is False
    assert result.reason_code == reason_codes.MANDATE_CATEGORY_FORBIDDEN


def test_currency_mismatch_is_rejected() -> None:
    private_key, public_key = generate_ed25519_keypair()
    mandate = _signed_mandate(private_key, currency="INR")

    result = verify_mandate(
        mandate,
        encode_key(public_key),
        current_status=MandateStatus.ACTIVE,
        requested_currency="USD",
    )

    assert result.valid is False
    assert result.reason_code == reason_codes.MANDATE_CURRENCY_MISMATCH
