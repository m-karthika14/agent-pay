"""
Purpose: A user's own "Automatic Payments" authorization -- HOW AgentPay is
permitted to pay, deliberately separate from the AI Shopping Budget/Mandate
(WHAT the AI is allowed to buy/spend, app.budgets.service /
app.mandates.service). A transaction is only ever automatically executed
when BOTH are valid.

Responsibilities:
- create_payment_authorization_setup(): start the ONE interactive Razorpay
  Checkout transaction that registers a reusable payment token.
- confirm_payment_authorization(): verify that transaction actually
  succeeded (never trust the frontend's say-so), extract the resulting
  token, and mark this user's authorization ACTIVE -- replacing, never
  silently deleting, any prior one.
- get_active_payment_authorization() / revoke_payment_authorization(): read
  and revoke, mirroring app.budgets.service's shape.
- execute_authorized_payment(): the ONLY function that can move money
  without a human present in a browser. Called exclusively from
  app.payments.checkout.create_checkout_session(), itself only reachable
  after every existing mandate/hard-policy/Intent Gate check has already
  passed and the cart is FROZEN -- never by Claude, the Merchant Agent, or
  a raw frontend request.
"""
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import append_event
from app.core.config import get_settings
from app.db.models.cart import Cart
from app.db.models.mandate import Mandate
from app.db.models.order import Order
from app.db.models.payment_authorization import PaymentAuthorization, PaymentAuthorizationStatus
from app.db.models.user import User
from app.mandates.service import to_signed_mandate
from app.payments import razorpay_client
from app.payments import reconciliation
from app.policy import reason_codes
from app.schemas.audit import AuditEventInput
from app.schemas.common import NotFoundError, ValidationError
from app.schemas.payment_authorization import (
    ConfirmPaymentAuthorizationRequest,
    PaymentAuthorizationResponse,
    SetupPaymentAuthorizationRequest,
    SetupPaymentAuthorizationResponse,
)

# How long a registered payment token is considered valid for automatic
# charges, absent any more specific Razorpay-reported expiry. This is an
# AgentPay-side ceiling on top of whatever Razorpay itself enforces, not a
# claim about the token's real-world validity period.
_DEFAULT_AUTHORIZATION_VALIDITY_DAYS = 180


def _to_response(row: PaymentAuthorization | None) -> PaymentAuthorizationResponse:
    is_active = (
        row is not None
        and row.status == PaymentAuthorizationStatus.ACTIVE
        and (row.expires_at is None or row.expires_at > datetime.now(UTC))
    )
    if not is_active or row is None:
        return PaymentAuthorizationResponse(is_active=False)
    return PaymentAuthorizationResponse(
        is_active=True,
        status=row.status.value,
        provider=row.provider,
        currency=row.currency,
        max_amount_minor=row.max_amount_minor,
        authorized_at=row.authorized_at,
        expires_at=row.expires_at,
    )


async def _get_user_or_raise(session: AsyncSession, user_id: uuid.UUID) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise NotFoundError("USER_NOT_FOUND", f"No user with id '{user_id}'.")
    return user


async def _get_active_row(session: AsyncSession, user_id: uuid.UUID) -> PaymentAuthorization | None:
    result = await session.execute(
        select(PaymentAuthorization)
        .where(PaymentAuthorization.user_id == user_id, PaymentAuthorization.status == PaymentAuthorizationStatus.ACTIVE)
        .order_by(PaymentAuthorization.created_at.desc())
        .limit(1)
    )
    row = result.scalar_one_or_none()
    if row is not None and row.expires_at is not None and row.expires_at <= datetime.now(UTC):
        return None
    return row


async def get_active_payment_authorization(session: AsyncSession, user_id: uuid.UUID) -> PaymentAuthorizationResponse:
    """Fetch a user's active Automatic Payments authorization (is_active=False, not an error, if none/expired)."""
    row = await _get_active_row(session, user_id)
    return _to_response(row)


async def create_payment_authorization_setup(
    session: AsyncSession, user_id: uuid.UUID, body: SetupPaymentAuthorizationRequest
) -> SetupPaymentAuthorizationResponse:
    """
    Start the ONE interactive Razorpay Checkout transaction that registers a
    reusable payment token (Razorpay's Recurring Payments -- Custom
    Integration flow). Creates a Razorpay Customer + a registration Order,
    and a local PENDING row to track the in-progress setup -- NOT yet
    usable authority; only confirm_payment_authorization() can activate it.
    """
    user = await _get_user_or_raise(session, user_id)

    # Razorpay requires a contact on the customer for the recurring
    # registration order below. Prefer the user's own phone; fall back to
    # the configured setup contact (Test Mode) when they have none.
    customer = razorpay_client.create_customer(
        name=user.name,
        email=user.email,
        contact=user.phone or get_settings().razorpay_setup_contact,
    )
    customer_id = customer["id"]

    # The registration transaction's own amount is the buyer's stated
    # ceiling itself -- Razorpay requires a real, non-zero first payment to
    # establish the token; charging the full ceiling up front (refundable in
    # Test Mode, and a real business would size this deliberately) is the
    # simplest choice that doesn't invent an arbitrary registration fee.
    order = razorpay_client.create_recurring_registration_order(
        amount_minor=body.max_amount_minor,
        currency=body.currency,
        receipt=f"payment-auth-setup-{uuid.uuid4().hex[:8]}",
        customer_id=customer_id,
        max_amount_minor=body.max_amount_minor,
    )

    row = PaymentAuthorization(
        user_id=user_id,
        provider="razorpay",
        razorpay_customer_id=customer_id,
        razorpay_token_id=None,
        setup_razorpay_order_id=order["id"],
        status=PaymentAuthorizationStatus.PENDING,
        currency=body.currency,
        max_amount_minor=body.max_amount_minor,
    )
    session.add(row)
    await session.flush()

    await append_event(
        session,
        AuditEventInput(
            event_type="PAYMENT_AUTHORIZATION_CREATED",
            actor_type="USER",
            payload={
                "razorpay_order_id": order["id"],
                "max_amount_minor": body.max_amount_minor,
                "currency": body.currency,
            },
            user_id=str(user_id),
        ),
    )

    return SetupPaymentAuthorizationResponse(
        razorpay_order_id=order["id"],
        razorpay_key_id=get_settings().razorpay_key_id,
        razorpay_customer_id=customer_id,
        amount_minor=body.max_amount_minor,
        currency=body.currency,
    )


async def confirm_payment_authorization(
    session: AsyncSession, user_id: uuid.UUID, body: ConfirmPaymentAuthorizationRequest
) -> PaymentAuthorizationResponse:
    """
    Verify the ONE interactive registration transaction actually succeeded
    -- fetching it directly from Razorpay, never trusting the frontend's
    claim alone -- extract the resulting token, and mark this user's
    authorization ACTIVE. Any prior ACTIVE authorization for this user is
    explicitly REVOKED first (never silently deleted, never left active
    alongside a new one).

    Raises:
        NotFoundError: If no PENDING setup row matches this order for this user.
        ValidationError: If Razorpay reports the payment did not succeed, or
            the payment doesn't actually belong to this order/customer.
    """
    result = await session.execute(
        select(PaymentAuthorization).where(
            PaymentAuthorization.user_id == user_id,
            PaymentAuthorization.setup_razorpay_order_id == body.razorpay_order_id,
            PaymentAuthorization.status == PaymentAuthorizationStatus.PENDING,
        )
    )
    pending_row = result.scalar_one_or_none()
    if pending_row is None:
        raise NotFoundError(
            "PAYMENT_AUTHORIZATION_SETUP_NOT_FOUND",
            f"No pending payment authorization setup for order '{body.razorpay_order_id}'.",
        )

    payment = razorpay_client.fetch_payment(body.razorpay_payment_id)
    if payment.get("order_id") != body.razorpay_order_id:
        raise ValidationError(
            "PAYMENT_AUTHORIZATION_MISMATCH",
            "The confirmed payment does not belong to this authorization's registration order.",
        )
    if payment.get("status") not in ("captured", "authorized"):
        pending_row.status = PaymentAuthorizationStatus.FAILED
        await session.flush()
        await append_event(
            session,
            AuditEventInput(
                event_type="AUTOMATIC_PAYMENT_FAILED",
                actor_type="SYSTEM",
                payload={"razorpay_order_id": body.razorpay_order_id, "razorpay_status": payment.get("status")},
                user_id=str(user_id),
            ),
        )
        raise ValidationError(
            reason_codes.PAYMENT_AUTHORIZATION_INVALID,
            f"Razorpay reports this registration payment as '{payment.get('status')}', not successful.",
        )

    token_id = payment.get("token_id")
    if not token_id:
        raise ValidationError(
            reason_codes.PAYMENT_AUTHORIZATION_INVALID,
            "Razorpay did not return a reusable token for this payment -- the selected payment method "
            "may not support Recurring Payments, or the account's Recurring Payments feature may not be "
            "enabled. Automatic Payments cannot be activated without a real token.",
        )

    # Explicitly REVOKE any prior ACTIVE authorization -- never leave two
    # ACTIVE rows, never silently delete the old one.
    previous = await _get_active_row(session, user_id)
    if previous is not None:
        previous.status = PaymentAuthorizationStatus.REVOKED
        await append_event(
            session,
            AuditEventInput(
                event_type="PAYMENT_AUTHORIZATION_REVOKED",
                actor_type="SYSTEM",
                payload={"reason": "replaced_by_new_authorization"},
                user_id=str(user_id),
            ),
        )

    pending_row.razorpay_token_id = token_id
    pending_row.status = PaymentAuthorizationStatus.ACTIVE
    pending_row.authorized_at = datetime.now(UTC)
    pending_row.expires_at = datetime.now(UTC) + timedelta(days=_DEFAULT_AUTHORIZATION_VALIDITY_DAYS)
    await session.flush()

    await append_event(
        session,
        AuditEventInput(
            event_type="PAYMENT_AUTHORIZATION_ACTIVATED",
            actor_type="SYSTEM",
            payload={"max_amount_minor": pending_row.max_amount_minor, "currency": pending_row.currency},
            user_id=str(user_id),
        ),
    )

    return _to_response(pending_row)


async def revoke_payment_authorization(session: AsyncSession, user_id: uuid.UUID) -> PaymentAuthorizationResponse:
    """Revoke a user's active Automatic Payments authorization. AgentPay must stop attempting automatic payment immediately after this."""
    row = await _get_active_row(session, user_id)
    if row is not None:
        row.status = PaymentAuthorizationStatus.REVOKED
        await session.flush()
        await append_event(
            session,
            AuditEventInput(
                event_type="PAYMENT_AUTHORIZATION_REVOKED",
                actor_type="USER",
                payload={"reason": "user_requested"},
                user_id=str(user_id),
            ),
        )
    return PaymentAuthorizationResponse(is_active=False)


async def execute_authorized_payment(session: AsyncSession, cart: Cart, order: Order, mandate_row: Mandate) -> str:
    """
    Attempt to automatically execute payment for a just-created, unpaid
    Order, using the cart owner's active payment authorization if eligible.

    Called ONLY from app.payments.checkout.create_checkout_session(), for a
    freshly-created (not idempotently-reused) Order against a cart that has
    already passed every existing hard-check/Intent Gate/mandate validation
    (that's what "FROZEN" already means by the time this runs) -- this
    function adds exactly the payment-authorization-specific checks on top,
    it never re-implements checks that already ran.

    Returns:
        One of "NO_AUTHORIZATION" (no active payment authorization -- caller
        falls back to the existing manual flow, unchanged), "INVALID"
        (authorization exists but doesn't cover this transaction),
        "CAPTURED", "REQUIRES_AUTHENTICATION", or "FAILED". Only "CAPTURED"
        means the order is now genuinely PAID.
    """
    auth_row = await _get_active_row(session, cart.user_id)
    if auth_row is None:
        return "NO_AUTHORIZATION"

    # Defense in depth (redundant with request_checkout()'s own hard checks,
    # which already guarantee order.amount_minor <= the mandate's cap by the
    # time a cart can even reach FROZEN -- checked again here so a payment
    # execution path never silently trusts an assumption made elsewhere).
    signed_mandate = to_signed_mandate(mandate_row)
    if order.amount_minor > signed_mandate.payload.max_amount:
        await append_event(
            session,
            AuditEventInput(
                event_type="AUTOMATIC_PAYMENT_FAILED",
                actor_type="SYSTEM",
                payload={"order_id": str(order.id), "amount_minor": order.amount_minor},
                decision="BLOCK",
                reason_code=reason_codes.PAYMENT_BLOCKED_BUDGET_EXCEEDED,
                order_id=str(order.id),
                mandate_id=str(mandate_row.id),
            ),
        )
        return "INVALID"

    if order.amount_minor > auth_row.max_amount_minor:
        await append_event(
            session,
            AuditEventInput(
                event_type="AUTOMATIC_PAYMENT_FAILED",
                actor_type="SYSTEM",
                payload={"order_id": str(order.id), "amount_minor": order.amount_minor},
                decision="BLOCK",
                reason_code=reason_codes.PAYMENT_AUTHORIZATION_INVALID,
                order_id=str(order.id),
                mandate_id=str(mandate_row.id),
            ),
        )
        return "INVALID"

    user = await session.get(User, cart.user_id)

    await append_event(
        session,
        AuditEventInput(
            event_type="AUTOMATIC_PAYMENT_STARTED",
            actor_type="SYSTEM",
            payload={"order_id": str(order.id), "amount_minor": order.amount_minor},
            order_id=str(order.id),
            mandate_id=str(mandate_row.id),
        ),
    )

    try:
        payment = razorpay_client.create_recurring_payment(
            amount_minor=order.amount_minor,
            currency=order.currency,
            razorpay_order_id=order.razorpay_order_id,
            customer_id=auth_row.razorpay_customer_id,
            token_id=auth_row.razorpay_token_id,
            email=user.email if user else "",
            # Razorpay's Recurring "Charge Payment" API requires a non-empty
            # contact -- an empty string is rejected with "The contact field
            # is required", failing every off-session charge regardless of
            # amount. Use the buyer's own phone, falling back to the
            # configured setup contact.
            contact=(user.phone if user and user.phone else get_settings().razorpay_setup_contact),
            description=f"AgentPay automatic purchase (cart {cart.id})",
        )
    except Exception as exc:  # noqa: BLE001 -- Razorpay SDK raises varied error types; never let one crash checkout
        requires_auth = _looks_like_authentication_required(exc)
        await append_event(
            session,
            AuditEventInput(
                event_type="AUTOMATIC_PAYMENT_REQUIRES_AUTHENTICATION" if requires_auth else "AUTOMATIC_PAYMENT_FAILED",
                actor_type="SYSTEM",
                payload={"order_id": str(order.id), "error": str(exc)[:1500]},
                decision="BLOCK" if not requires_auth else None,
                order_id=str(order.id),
                mandate_id=str(mandate_row.id),
            ),
        )
        return "REQUIRES_AUTHENTICATION" if requires_auth else "FAILED"

    payment_status = payment.get("status")
    if payment_status in ("captured", "authorized"):
        await append_event(
            session,
            AuditEventInput(
                event_type="AUTOMATIC_PAYMENT_AUTHORIZED",
                actor_type="SYSTEM",
                payload={"order_id": str(order.id), "razorpay_payment_id": payment.get("id")},
                order_id=str(order.id),
                mandate_id=str(mandate_row.id),
            ),
        )
        if payment_status == "authorized":
            try:
                razorpay_client.capture_payment_if_needed(payment["id"], order.amount_minor)
            except Exception:  # noqa: BLE001 -- reconcile_order_state below is the real source of truth either way
                pass
        # Reuses the EXISTING reconciliation path (the same one the webhook
        # calls) to pull Razorpay's own authoritative state and mark the
        # order/transaction/mandate exactly as it would for any other
        # payment -- never a second, parallel state-mutation implementation.
        await reconciliation.reconcile_order_state(session, order)
        if order.status == "PAID":
            await append_event(
                session,
                AuditEventInput(
                    event_type="AUTOMATIC_PAYMENT_CAPTURED",
                    actor_type="SYSTEM",
                    payload={"order_id": str(order.id), "razorpay_payment_id": payment.get("id")},
                    order_id=str(order.id),
                    mandate_id=str(mandate_row.id),
                ),
            )
            return "CAPTURED"
        return "REQUIRES_AUTHENTICATION"

    requires_auth = payment_status not in ("failed",)
    await append_event(
        session,
        AuditEventInput(
            event_type="AUTOMATIC_PAYMENT_REQUIRES_AUTHENTICATION" if requires_auth else "AUTOMATIC_PAYMENT_FAILED",
            actor_type="SYSTEM",
            payload={"order_id": str(order.id), "razorpay_status": payment_status},
            order_id=str(order.id),
            mandate_id=str(mandate_row.id),
        ),
    )
    return "REQUIRES_AUTHENTICATION" if requires_auth else "FAILED"


def _looks_like_authentication_required(exc: Exception) -> bool:
    """
    Best-effort classification of a Razorpay SDK exception as "needs
    additional customer authentication" vs. a hard failure -- Razorpay's
    Recurring Payments API can reject a charge attempt this way depending on
    the card network/bank's own rules, and AgentPay must surface that
    distinctly (PAYMENT_REQUIRES_AUTHENTICATION) rather than a generic
    failure, per the explicit requirement to never pretend success but also
    not conflate "needs another factor" with "permanently failed."

    NOT verified against a live Razorpay account in this environment (no
    test credentials with Recurring Payments enabled were available) -- the
    exact substrings Razorpay's SDK/API actually raise for this case should
    be confirmed against a real account before relying on this in production;
    see the final report for what still needs live verification.
    """
    message = str(exc).lower()
    return any(term in message for term in ("authentication", "3ds", "otp", "requires_authentication"))
