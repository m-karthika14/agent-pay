"""
Purpose: Verify Razorpay HMAC-SHA256 signatures (plan.md Section 16.3).

Responsibilities:
- verify_payment_signature(): checks the signature Razorpay's Standard
  Checkout returns to the frontend after a successful payment
  (order_id + "|" + payment_id, signed with the Key Secret).
- verify_webhook_signature(): checks the `X-Razorpay-Signature` header on
  an incoming webhook POST, signed over the RAW request body with the
  separate Webhook Secret.

Both delegate to the official Razorpay SDK's `utility.verify_signature`
(HMAC-SHA256 via `hmac.compare_digest`, so comparison is constant-time) but
normalize its behavior to AgentPay's fail-closed style: return False on any
failure rather than raising, matching app.security.signing.verify_signature
so callers never need a try/except to implement "reject on failure."

This module must never call an LLM. It also never constructs a Razorpay
client itself -- app.payments.razorpay_client owns that.
"""
from razorpay import Client
from razorpay.errors import SignatureVerificationError

from app.core.config import get_settings


def verify_payment_signature(razorpay_order_id: str, razorpay_payment_id: str, razorpay_signature: str) -> bool:
    """
    Verify the signature returned by Razorpay Standard Checkout's success
    handler after a payment completes client-side.

    Args:
        razorpay_order_id: The order id Checkout was opened with.
        razorpay_payment_id: The payment id Razorpay reports as completed.
        razorpay_signature: The signature Razorpay attaches to the result.

    Returns:
        True if the signature is valid for this exact (order_id, payment_id)
        pair under AgentPay's Key Secret; False for any failure (wrong
        secret, tampered ids, malformed signature). Never raises.
    """
    settings = get_settings()
    client = Client(auth=(settings.razorpay_key_id, settings.razorpay_key_secret))
    try:
        return client.utility.verify_payment_signature(
            {
                "razorpay_order_id": razorpay_order_id,
                "razorpay_payment_id": razorpay_payment_id,
                "razorpay_signature": razorpay_signature,
            }
        )
    except SignatureVerificationError:
        return False


def verify_webhook_signature(raw_body: bytes, signature: str) -> bool:
    """
    Verify the `X-Razorpay-Signature` header on an incoming webhook request.

    Args:
        raw_body: The EXACT raw request body bytes as received -- per
            plan.md Section 16.3, webhook verification must use the raw
            body, never a re-serialized/re-parsed version of it (any
            re-encoding could change the bytes and break the signature).
        signature: The `X-Razorpay-Signature` header value.

    Returns:
        True if the signature is valid under AgentPay's Webhook Secret;
        False for any failure. Never raises.
    """
    settings = get_settings()
    client = Client(auth=(settings.razorpay_key_id, settings.razorpay_key_secret))
    try:
        return client.utility.verify_webhook_signature(
            raw_body.decode("utf-8"), signature, settings.razorpay_webhook_secret
        )
    except SignatureVerificationError:
        return False
