"""
Purpose: High-level, deterministic verification of a signed AgentPay mandate.

Responsibilities:
- Combine canonicalization + Ed25519 signature verification with the
  mandate's business-level validity rules (merchant, amount, category,
  currency, expiry, single-use/replay state), per plan.md Section 9.4.
- Return a single deterministic VerificationResult — never raise for an
  invalid mandate, and never guess: any failure fails closed.

This module must never call an LLM or Razorpay. It also never touches the
database directly — callers (e.g. app.mandates.service) are responsible for
looking up a mandate's current persisted status and passing it in as
`current_status`, keeping this function pure and easy to unit test.
"""
import base64
from datetime import UTC, datetime

from app.policy import reason_codes
from app.schemas.mandate import MandateStatus, MandateVerificationResult, SignedMandate
from app.security.canonical import canonicalize_mandate
from app.security.signing import decode_public_key, verify_signature


def verify_mandate(
    mandate: SignedMandate,
    public_key_b64: str,
    *,
    current_status: MandateStatus,
    now: datetime | None = None,
    expected_merchant_id: str | None = None,
    requested_amount: int | None = None,
    requested_category: str | None = None,
    requested_currency: str | None = None,
) -> MandateVerificationResult:
    """
    Deterministically verify a signed mandate, per plan.md Section 9.4.

    Args:
        mandate: The signed mandate to verify.
        public_key_b64: Base64-encoded Ed25519 public key expected to have
            signed this mandate (the merchant's AgentPay signing key).
        current_status: The mandate's current persisted lifecycle status
            (looked up by the caller from the `mandates` table). Required —
            a mandate's replay/single-use state cannot be determined from
            the payload alone.
        now: Current time for expiry comparison. Defaults to real UTC now;
            tests may inject a fixed value.
        expected_merchant_id: If provided, the mandate must have been issued
            for this merchant. Omit when only checking mandate integrity
            with no specific request context yet.
        requested_amount: If provided, must not exceed the mandate's
            max_amount (minor units). Omit when no specific request exists.
        requested_category: If provided, must be in the mandate's
            allowed_categories.
        requested_currency: If provided, must match the mandate's currency.

    Returns:
        MandateVerificationResult. `valid=True` only if every applicable
        check passes. On the first failing check, verification stops
        immediately and returns that failure — checks are not partially
        run past the first BLOCK, mirroring the fail-fast behavior required
        of the deterministic policy engine (plan.md Section 11.2).
    """
    now = now or datetime.now(UTC)
    payload = mandate.payload

    # Step 1-3: canonicalize + decode signature + verify Ed25519 signature.
    # This runs first: an unsigned or tampered mandate must never leak
    # information about *why* it would otherwise be valid or invalid.
    canonical_bytes = canonicalize_mandate(payload)
    try:
        public_key = decode_public_key(public_key_b64)
        signature_bytes = _decode_signature(mandate.signature)
    except (ValueError, TypeError):
        return MandateVerificationResult(
            valid=False,
            reason_code=reason_codes.MANDATE_INVALID_SIGNATURE,
            reason="Signature or public key could not be decoded.",
        )

    if not verify_signature(canonical_bytes, signature_bytes, public_key):
        return MandateVerificationResult(
            valid=False,
            reason_code=reason_codes.MANDATE_INVALID_SIGNATURE,
            reason="Ed25519 signature verification failed.",
        )

    # Step 4: validate merchant.
    if expected_merchant_id is not None and payload.merchant_id != expected_merchant_id:
        return MandateVerificationResult(
            valid=False,
            reason_code=reason_codes.MANDATE_MERCHANT_MISMATCH,
            reason=f"Mandate is for merchant '{payload.merchant_id}', not '{expected_merchant_id}'.",
        )

    # Step 5: validate amount.
    if requested_amount is not None and requested_amount > payload.max_amount:
        return MandateVerificationResult(
            valid=False,
            reason_code=reason_codes.MANDATE_AMOUNT_EXCEEDED,
            reason=(
                f"Requested amount {requested_amount} exceeds mandate cap "
                f"{payload.max_amount}."
            ),
        )

    # Step 6: validate category + currency.
    if requested_category is not None and requested_category not in payload.allowed_categories:
        return MandateVerificationResult(
            valid=False,
            reason_code=reason_codes.MANDATE_CATEGORY_FORBIDDEN,
            reason=f"Category '{requested_category}' is not in the mandate's allowed categories.",
        )
    if requested_currency is not None and requested_currency != payload.currency:
        return MandateVerificationResult(
            valid=False,
            reason_code=reason_codes.MANDATE_CURRENCY_MISMATCH,
            reason=f"Requested currency '{requested_currency}' does not match mandate currency '{payload.currency}'.",
        )

    # Step 7: validate expiry.
    if payload.expires_at <= now:
        return MandateVerificationResult(
            valid=False,
            reason_code=reason_codes.MANDATE_EXPIRED,
            reason=f"Mandate expired at {payload.expires_at.isoformat()}.",
        )

    # Step 8-9: validate single-use state / replay.
    if current_status != MandateStatus.ACTIVE:
        if current_status == MandateStatus.CONSUMED and payload.single_use:
            return MandateVerificationResult(
                valid=False,
                reason_code=reason_codes.REPLAY_DETECTED,
                reason="Single-use mandate has already been consumed.",
            )
        return MandateVerificationResult(
            valid=False,
            reason_code=reason_codes.MANDATE_ALREADY_CONSUMED,
            reason=f"Mandate is not active (status={current_status.value}).",
        )

    # Step 10: all checks passed.
    return MandateVerificationResult(valid=True)


def _decode_signature(signature_b64: str) -> bytes:
    """Decode the mandate's base64 signature string into raw bytes."""
    return base64.b64decode(signature_b64)
