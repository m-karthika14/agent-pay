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
from datetime import UTC, datetime, timedelta
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


def fetch_order_payments(razorpay_order_id: str) -> list[dict[str, Any]]:
    """
    List every payment attempt made against a Razorpay order.

    Used by reconciliation (app.payments.reconciliation.reconcile_order_state)
    to find the actual captured payment id when a webhook never arrived --
    AgentPay's own Transaction row has no payment id in exactly that
    situation, so it can't be looked up locally and must come from Razorpay.
    """
    client = get_razorpay_client()
    return client.order.payments(razorpay_order_id)["items"]


def create_customer(name: str, email: str) -> dict[str, Any]:
    """
    Create (or, if Razorpay already has one for this email, return the
    existing) Razorpay Customer -- the account a payment token is saved
    against, for Automatic Payments setup (app.payments.authorization_service).

    Verified live against a real Razorpay Test Mode account: a duplicate
    Customer.create() call for an already-registered email raises
    razorpay.errors.BadRequestError("Customer already exists for the
    merchant") -- carrying no structured error body at all in this SDK
    version (no `.error`/`.metadata` attribute, just a plain message
    string), so the existing customer's id cannot be recovered from the
    exception itself. This falls back to listing customers and matching by
    email client-side instead (Razorpay's Customer API has no server-side
    email filter in this SDK version either).

    Args:
        name: The buyer's display name.
        email: The buyer's email -- Razorpay's own de-duplication key.

    Returns:
        The raw Razorpay customer dict (contains "id", "name", "email").

    Raises:
        The original SDK exception, if the create failed for a reason other
        than an already-existing customer for this email.
    """
    client = get_razorpay_client()
    try:
        return client.customer.create({"name": name, "email": email})
    except Exception as exc:  # noqa: BLE001 -- see docstring: this SDK's BadRequestError carries no structured body
        if "already exists" not in str(exc).lower():
            raise
        existing = next((c for c in client.customer.all({"count": 100})["items"] if c.get("email") == email), None)
        if existing is None:
            raise
        return existing


def create_recurring_registration_order(
    amount_minor: int, currency: str, receipt: str, customer_id: str, max_amount_minor: int
) -> dict[str, Any]:
    """
    Create the Razorpay Order for the ONE interactive transaction that
    registers a reusable payment token (Razorpay's Recurring Payments --
    Custom Integration flow: https://razorpay.com/docs/api/payments/recurring-payments/custom/).

    The buyer completes this single order via normal Razorpay Checkout
    (full authentication, exactly like any other payment -- never bypassed).
    Once captured, the resulting payment carries a `token_id` that
    app.payments.razorpay_client.create_recurring_payment() can later charge
    without the buyer present, up to `max_amount_minor` per Razorpay's own
    token-validity rules.

    IMPORTANT -- verified live against a real Razorpay Test Mode account
    (this project's own configured RAZORPAY_KEY_ID/SECRET), not assumed from
    documentation alone:
    - `token.expire_at` must be a real Unix epoch integer -- Razorpay
      rejects `None` outright ("expire_at must be an integer"), unlike what
      an initial reading of the docs suggested.
    - An explicit `"recurring": "1"` field is REJECTED by this account
      ("recurring is/are not required and should not be sent") -- omitted
      here; `method: "card"` + a `token` block alone is what this account's
      API actually expects to mark an order as a token-registration order.
    - With the fields above (and no `recurring` flag), this account's API
      still responded "The contact field is required for recurring links";
      adding `contact`/`email` at the order level then flipped to "contact
      is/are not required and should not be sent" -- these two responses
      contradict each other, which was not resolved within this session.
      This strongly suggests this specific Test Mode account does not have
      Razorpay's Recurring Payments feature enabled (a business-level
      capability Razorpay grants, not something a bare API key unlocks) --
      its validation logic for a feature it doesn't have active appears to
      produce inconsistent error text rather than a single clear "not
      enabled" message. See the Phase 5 final report for what this means
      end-to-end and what Razorpay-side action would resolve it.

    Args:
        amount_minor: The registration transaction's own amount (the first
            real charge, in minor units) -- Razorpay requires a real payment
            to establish the token, there is no zero-amount registration.
        currency: ISO 4217 currency code.
        receipt: Caller-supplied receipt reference.
        customer_id: The Razorpay Customer this token will be saved against.
        max_amount_minor: The ceiling this token registration itself permits
            for future recurring charges.

    Returns:
        The raw Razorpay order dict.

    Raises:
        razorpay.errors.BadRequestError: If this Razorpay account does not
            support this order shape (see the note above) -- surfaces to
            the setup caller as a real, honest failure, never faked success.
    """
    client = get_razorpay_client()
    max_amount_minor = max(max_amount_minor, amount_minor)
    expire_at = int((datetime.now(UTC) + timedelta(days=180)).timestamp())
    return client.order.create(
        {
            "amount": amount_minor,
            "currency": currency,
            "receipt": receipt,
            "customer_id": customer_id,
            "method": "card",
            "token": {"max_amount": max_amount_minor, "expire_at": expire_at},
            "payment_capture": 1,
        }
    )


def create_recurring_payment(
    *,
    amount_minor: int,
    currency: str,
    razorpay_order_id: str,
    customer_id: str,
    token_id: str,
    email: str,
    contact: str,
    description: str,
) -> dict[str, Any]:
    """
    Charge a previously-registered token against a fresh order, with the
    buyer NOT present -- Razorpay's Recurring Payments "Charge Payment" API
    (client.payment.createRecurring, POST /v1/payments/create/recurring).

    This is the ONLY function in this module that can move money without a
    human actively completing Razorpay Checkout in a browser -- it is called
    exclusively from app.payments.authorization_service.execute_authorized_payment(),
    itself only reachable after every existing mandate/policy/Intent Gate
    check has already passed on a FROZEN cart (never by Claude, the Merchant
    Agent, or a raw frontend request).

    Depending on the card/network's own rules, Razorpay may still require
    additional customer authentication for a given charge despite the
    registered token -- callers must not assume success from a non-raising
    return alone; inspect the returned dict's "status" field (see
    app.payments.authorization_service for the full state mapping) and treat
    an SDK exception as a hard stop (PAYMENT_FAILED/PAYMENT_REQUIRES_AUTHENTICATION),
    never as an ambiguous success.

    Args:
        amount_minor: The actual amount to charge, in minor units -- always
            the server-side frozen cart's own total, never a caller-supplied
            value.
        currency: ISO 4217 currency code.
        razorpay_order_id: The order (already created via create_order(),
            same as any other AgentPay checkout) this charge is for.
        customer_id: The Razorpay Customer the token belongs to.
        token_id: The saved payment token to charge.
        email: The buyer's email (Razorpay's Recurring Payments API requires
            it on the charge request itself, not just on the Customer).
        contact: The buyer's phone number, in the same E.164-ish shape
            Razorpay's Customer API expects.
        description: A short, human-readable description of the charge.

    Returns:
        The raw Razorpay payment dict.
    """
    client = get_razorpay_client()
    return client.payment.createRecurring(
        {
            "email": email,
            "contact": contact,
            "amount": amount_minor,
            "currency": currency,
            "order_id": razorpay_order_id,
            "customer_id": customer_id,
            "token": token_id,
            "recurring": "1",
            "description": description,
        }
    )


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
