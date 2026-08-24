"""
Purpose: Verify that mandate canonicalization is deterministic.

A signature is only meaningful if canonicalize_mandate() always produces the
same bytes for the same logical mandate. If canonicalization were unstable,
a validly-signed mandate could spuriously fail verification, or worse, two
different-looking-but-equal payloads could hash/sign differently in ways
that break replay/idempotency assumptions elsewhere in the system.
"""
from datetime import UTC, datetime

from app.schemas.mandate import MandateIntent, MandatePayload
from app.security.canonical import canonicalize_mandate


def _sample_payload(**overrides: object) -> MandatePayload:
    defaults: dict[str, object] = {
        "mandate_id": "M-001",
        "merchant_id": "urbannest",
        "currency": "INR",
        "max_amount": 300000,
        "allowed_categories": ["electronics"],
        "allow_addons": False,
        "delivery_requirement": "under_3_days",
        "single_use": True,
        "expires_at": datetime(2026, 9, 1, tzinfo=UTC),
        "intent": MandateIntent(product_type="wireless earbuds", notes="no accessories"),
    }
    defaults.update(overrides)
    return MandatePayload(**defaults)  # type: ignore[arg-type]


def test_canonicalization_is_deterministic() -> None:
    """The same logical payload must canonicalize to byte-identical output every time."""
    payload = _sample_payload()

    first = canonicalize_mandate(payload)
    second = canonicalize_mandate(payload)

    assert first == second


def test_canonicalization_is_independent_of_category_order() -> None:
    """Category list order is not semantically meaningful and must not affect the bytes."""
    payload_a = _sample_payload(allowed_categories=["electronics", "accessories"])
    payload_b = _sample_payload(allowed_categories=["accessories", "electronics"])

    assert canonicalize_mandate(payload_a) == canonicalize_mandate(payload_b)


def test_canonicalization_changes_with_content() -> None:
    """A genuinely different mandate must canonicalize to different bytes."""
    payload_a = _sample_payload(max_amount=300000)
    payload_b = _sample_payload(max_amount=999900)

    assert canonicalize_mandate(payload_a) != canonicalize_mandate(payload_b)


def test_canonicalization_returns_utf8_bytes() -> None:
    """canonicalize_mandate() must return bytes, per plan.md Section 9.2 step 5."""
    payload = _sample_payload()

    result = canonicalize_mandate(payload)

    assert isinstance(result, bytes)
    # Must round-trip as valid UTF-8.
    result.decode("utf-8")
