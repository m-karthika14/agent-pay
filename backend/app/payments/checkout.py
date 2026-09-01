"""
Purpose: Create a Razorpay checkout session for an already-frozen cart
(plan.md Section 16.2).

This is the "complete" half of AgentPay's checkout API
(POST /api/checkout/{cart_id}/complete): it assumes
app.services.checkout_service.request_checkout() has already run the hard
checks and frozen the cart (plan.md Section 3 in the Phase 3 flow) --
create_checkout_session() itself performs no authorization checks. It only
creates the Razorpay order for an amount AgentPay has already approved.
"""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import append_event
from app.core.config import get_settings
from app.core.constants import CART_STATUS_FROZEN
from app.db.models.cart import Cart
from app.db.models.order import Order
from app.db.models.transaction import Transaction
from app.mandates.service import get_mandate_by_business_id
from app.payments import authorization_service
from app.payments.razorpay_client import create_order
from app.schemas.audit import AuditEventInput
from app.schemas.common import NotFoundError, ValidationError
from app.schemas.payment import CheckoutSessionResponse


def _idempotency_key_for(cart_id: uuid.UUID) -> str:
    """
    Deterministic idempotency key for one cart's checkout-completion request.

    A cart can only be usefully "completed" once, so keying on cart_id makes
    a retried POST /api/checkout/{cart_id}/complete naturally idempotent:
    the second call finds the existing Transaction row and returns the
    existing order instead of creating a second Razorpay order
    (plan.md Section 24.2).
    """
    return f"complete:{cart_id}"


def build_checkout_options(order: Order, auto_payment_status: str | None = None) -> CheckoutSessionResponse:
    """
    Build the exact, minimal set of fields a frontend needs to open Razorpay
    Standard Checkout for an order (plan.md Section 16.2).

    Args:
        order: A persisted Order row with razorpay_order_id already set.
        auto_payment_status: See CheckoutSessionResponse's docstring --
            None on every existing call site; set only by
            create_checkout_session() when Automatic Payments (plan.md
            Phase 5) was attempted for this order.

    Returns:
        CheckoutSessionResponse containing only the public Test Mode Key ID
        (never the Key Secret, per plan.md Section 6's "Secret rules") plus
        the order id, amount, and currency.
    """
    return CheckoutSessionResponse(
        order_id=str(order.id),
        razorpay_order_id=order.razorpay_order_id,
        razorpay_key_id=get_settings().razorpay_key_id,
        amount_minor=order.amount_minor,
        currency=order.currency,
        auto_payment_status=auto_payment_status,
    )


async def create_checkout_session(
    session: AsyncSession, cart_id: uuid.UUID, mandate_id: str
) -> CheckoutSessionResponse:
    """
    Create (or idempotently re-return) a Razorpay order for a frozen cart.

    Args:
        session: Active AsyncSession.
        cart_id: The cart to create a checkout session for. Must already be
            FROZEN (i.e. request_checkout() has already approved it).
        mandate_id: Business-facing mandate_id authorizing this cart, used
            to link the resulting Order back to its mandate.

    Returns:
        CheckoutSessionResponse with the Razorpay order id, the public Test
        Mode Key ID, and the amount/currency -- everything a frontend needs
        to open Razorpay Standard Checkout, and nothing secret.

    Raises:
        NotFoundError: If the cart or mandate does not exist.
        ValidationError: If the cart has not been frozen yet (checkout was
            never requested, or was blocked).
    """
    cart = await session.get(Cart, cart_id)
    if cart is None:
        raise NotFoundError("CART_NOT_FOUND", f"No cart with id '{cart_id}'.")
    if cart.status != CART_STATUS_FROZEN:
        raise ValidationError(
            "CART_NOT_FROZEN",
            f"Cart '{cart_id}' has not passed checkout (status={cart.status}). "
            "Call POST /api/checkout/request first.",
        )

    mandate_row = await get_mandate_by_business_id(session, mandate_id)
    if mandate_row is None:
        raise NotFoundError("MANDATE_NOT_FOUND", f"No mandate with id '{mandate_id}'.")

    idempotency_key = _idempotency_key_for(cart.id)
    existing_result = await session.execute(
        select(Transaction, Order)
        .join(Order, Order.id == Transaction.order_id)
        .where(Transaction.idempotency_key == idempotency_key)
    )
    existing_row = existing_result.first()
    if existing_row is not None:
        _existing_txn, existing_order = existing_row
        return build_checkout_options(existing_order)

    order = Order(
        cart_id=cart.id,
        mandate_id=mandate_row.id,
        status="CREATED",
        amount_minor=cart.subtotal_minor,
        currency=cart.currency,
    )
    session.add(order)
    await session.flush()

    razorpay_order = create_order(
        amount_minor=cart.subtotal_minor, currency=cart.currency, receipt=str(cart.id)
    )
    order.razorpay_order_id = razorpay_order["id"]
    await session.flush()

    session.add(
        Transaction(
            order_id=order.id,
            status="PENDING",
            idempotency_key=idempotency_key,
        )
    )
    await session.flush()

    await append_event(
        session,
        AuditEventInput(
            event_type="RAZORPAY_ORDER_CREATED",
            actor_type="SYSTEM",
            payload={"cart_id": str(cart.id), "razorpay_order_id": order.razorpay_order_id},
            mandate_id=str(mandate_row.id),
            order_id=str(order.id),
        ),
    )

    # Automatic Payments (plan.md Phase 5): if this cart's owner has an
    # active, eligible payment authorization, attempt to execute payment
    # right here -- the existing manual flow (frontend opens Razorpay
    # Checkout for the human to pay) is otherwise completely unchanged.
    # Only ever reached for a FRESHLY-created order (the idempotency check
    # above already returned early for a retried/duplicate call), so this
    # can never run twice for the same checkout.
    auto_payment_status: str | None = None
    outcome = await authorization_service.execute_authorized_payment(session, cart, order, mandate_row)
    if outcome != "NO_AUTHORIZATION":
        auto_payment_status = outcome

    return build_checkout_options(order, auto_payment_status)
