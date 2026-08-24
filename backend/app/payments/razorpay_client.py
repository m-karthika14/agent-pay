"""
Purpose: Thin wrapper over the official Razorpay Python SDK (plan.md Section 16.1).

Responsibilities:
- Construct a single Razorpay client from Settings (Test Mode keys only).
- Expose the handful of SDK calls AgentPay actually needs: creating an
  order, fetching order/payment state, and capturing a payment if needed.

No other module should construct `razorpay.Client(...)` directly -- this
keeps the Key Secret's only usage site centralized and auditable, and means
callers never see raw SDK exceptions without going through this module's
docstrings about what each call does.
"""
from functools import lru_cache
from typing import Any

import razorpay

from app.core.config import get_settings


@lru_cache
def get_razorpay_client() -> razorpay.Client:
    """
    Return the process-wide Razorpay SDK client, built from Test Mode keys.

    Returns:
        A razorpay.Client authenticated with (RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET).
        Cached so the same client instance is reused across calls.
    """
    settings = get_settings()
    return razorpay.Client(auth=(settings.razorpay_key_id, settings.razorpay_key_secret))


def create_order(amount_minor: int, currency: str, receipt: str, notes: dict[str, str] | None = None) -> dict[str, Any]:
    """
    Create a Razorpay Order for a frozen, checked-out cart.

    Args:
        amount_minor: Order amount in the smallest currency unit (paise for INR),
            matching plan.md Section 8.3's money-storage convention.
        currency: ISO 4217 currency code, e.g. "INR".
        receipt: A caller-supplied receipt reference (AgentPay uses the cart id)
            so the order can be traced back to its cart without a lookup.
        notes: Optional small key/value metadata attached to the order.

    Returns:
        The raw Razorpay order dict (contains "id", "amount", "currency",
        "status", etc. per Razorpay's Orders API).
    """
    client = get_razorpay_client()
    return client.order.create(
        {
            "amount": amount_minor,
            "currency": currency,
            "receipt": receipt,
            "notes": notes or {},
        }
    )


def fetch_order(razorpay_order_id: str) -> dict[str, Any]:
    """Fetch the current state of a Razorpay order by its id."""
    client = get_razorpay_client()
    return client.order.fetch(razorpay_order_id)


def fetch_payment(razorpay_payment_id: str) -> dict[str, Any]:
    """Fetch the current state of a Razorpay payment by its id."""
    client = get_razorpay_client()
    return client.payment.fetch(razorpay_payment_id)


def capture_payment_if_needed(razorpay_payment_id: str, amount_minor: int) -> dict[str, Any]:
    """
    Capture an authorized-but-not-yet-captured payment.

    Standard Checkout with auto-capture enabled on the Razorpay dashboard
    normally captures automatically; this exists as an explicit fallback so
    AgentPay never silently leaves an authorized payment uncaptured.

    Args:
        razorpay_payment_id: The payment to capture.
        amount_minor: Amount to capture, in minor units -- must match the
            authorized amount exactly.

    Returns:
        The raw Razorpay payment dict after capture.
    """
    client = get_razorpay_client()
    return client.payment.capture(razorpay_payment_id, amount_minor)
