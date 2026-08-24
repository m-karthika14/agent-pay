"""
Purpose: Deterministic, canonical byte-serialization of a mandate payload.

Responsibilities:
- Produce the exact same bytes for the exact same logical mandate content,
  regardless of Python dict ordering, datetime representation, or numeric
  type quirks.
- Be the single function that sign_mandate() and verify_mandate() both call,
  so a signature is always checked against the same bytes it was created from.

This module must never call an LLM, Razorpay, or the database — it is pure,
side-effect-free serialization (plan.md Section 5.1 style module docstring).

Per plan.md Section 9.2: "Never sign a Python dictionary using arbitrary
serialization." We therefore use `json.dumps(..., sort_keys=True)` over an
explicitly normalized dict, rather than relying on Pydantic's default
`model_dump_json()` (whose field order/formatting is an implementation detail
we don't want signatures to depend on).
"""
import json

from app.schemas.mandate import MandatePayload


def canonicalize_mandate(payload: MandatePayload) -> bytes:
    """
    Serialize a MandatePayload into deterministic, signable UTF-8 bytes.

    Args:
        payload: The mandate content to canonicalize.

    Returns:
        UTF-8 encoded bytes. For the same logical payload, this function
        always returns byte-identical output:
        1. Field order is normalized (JSON object keys sorted).
        2. Dates are normalized to ISO 8601 UTC strings.
        3. Numeric types are normalized (ints stay ints; no float drift).
        4. Serialization uses a fixed separator style (no incidental
           whitespace differences between calls).
    """
    normalized = {
        "mandate_id": payload.mandate_id,
        "merchant_id": payload.merchant_id,
        "currency": payload.currency,
        "max_amount": int(payload.max_amount),
        "allowed_categories": sorted(payload.allowed_categories),
        "allow_addons": bool(payload.allow_addons),
        "delivery_requirement": payload.delivery_requirement,
        "single_use": bool(payload.single_use),
        "expires_at": payload.expires_at.isoformat(),
        "intent": {
            "product_type": payload.intent.product_type,
            "notes": payload.intent.notes,
        },
    }
    # sort_keys guarantees stable field order; separators strip incidental
    # whitespace so two equal dicts always produce identical bytes.
    canonical_json = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
    return canonical_json.encode("utf-8")
