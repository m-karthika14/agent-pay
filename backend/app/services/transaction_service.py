"""
Purpose: Read-only transaction lookups, including a transaction's full
audit trace (plan.md Section 18 — Transactions, Section 45).

This module only reads. All mutation of transactions happens in
app.payments.reconciliation, driven by webhook events.
"""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.carts.service import to_cart_response
from app.db.models.audit_event import AuditEvent
from app.db.models.cart import Cart
from app.db.models.cart_item import CartItem
from app.db.models.mandate import Mandate
from app.db.models.order import Order
from app.db.models.product import Product
from app.db.models.transaction import Transaction
from app.db.models.user import User
from app.mandates.service import to_signed_mandate
from app.schemas.common import NotFoundError
from app.schemas.payment import (
    BuyerSummary,
    MandateSummary,
    OrderHistoryEntry,
    OrderSummary,
    TransactionResponse,
    TransactionTraceEvent,
    TransactionTraceResponse,
)


def _to_transaction_response(row: Transaction) -> TransactionResponse:
    return TransactionResponse(
        transaction_id=str(row.id),
        order_id=str(row.order_id),
        razorpay_payment_id=row.razorpay_payment_id,
        status=row.status,
        failure_code=row.failure_code,
        failure_message=row.failure_message,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def get_transaction(session: AsyncSession, transaction_id: uuid.UUID) -> TransactionResponse:
    """
    Fetch a single transaction by id.

    Args:
        session: Active AsyncSession.
        transaction_id: The transaction to fetch.

    Returns:
        TransactionResponse.

    Raises:
        NotFoundError: If no transaction exists with that id.
    """
    row = await session.get(Transaction, transaction_id)
    if row is None:
        raise NotFoundError("TRANSACTION_NOT_FOUND", f"No transaction with id '{transaction_id}'.")
    return _to_transaction_response(row)


async def list_orders_for_user(session: AsyncSession, user_id: uuid.UUID) -> list[OrderHistoryEntry]:
    """
    List every order ever placed by a user, newest first (storefront
    "Buying History" tab).

    Orders don't carry user_id directly -- they're reached via
    Order.cart_id -> Cart.user_id, since a cart is always created for a
    specific buyer before any order exists.

    Args:
        session: Active AsyncSession.
        user_id: The buyer whose orders to list.

    Returns:
        OrderHistoryEntry list, newest order first. Empty if the user has
        never completed a checkout -- not an error, a normal new-buyer state.
    """
    orders_result = await session.execute(
        select(Order, Mandate.mandate_id)
        .join(Cart, Cart.id == Order.cart_id)
        .join(Mandate, Mandate.id == Order.mandate_id)
        .where(Cart.user_id == user_id)
        .order_by(Order.created_at.desc())
    )
    rows = orders_result.all()

    entries: list[OrderHistoryEntry] = []
    for order_row, business_mandate_id in rows:
        items_result = await session.execute(
            select(CartItem.quantity, Product.name)
            .join(Product, Product.id == CartItem.product_id)
            .where(CartItem.cart_id == order_row.cart_id)
        )
        item_summary = ", ".join(f"{quantity}x {name}" for quantity, name in items_result.all())
        entries.append(
            OrderHistoryEntry(
                order_id=str(order_row.id),
                mandate_id=business_mandate_id,
                status=order_row.status,
                amount_minor=order_row.amount_minor,
                currency=order_row.currency,
                item_summary=item_summary,
                created_at=order_row.created_at,
            )
        )
    return entries


async def get_transaction_trace(session: AsyncSession, transaction_id: uuid.UUID) -> TransactionTraceResponse:
    """
    Fetch a transaction plus everything the Merchant Console's Transaction
    view needs to render in one call (plan.md Section 19.2/24): the order,
    the cart in its final frozen state, the mandate that authorized it, the
    buyer, and the ordered audit decision trace.

    Args:
        session: Active AsyncSession.
        transaction_id: The transaction to trace.

    Returns:
        TransactionTraceResponse.

    Raises:
        NotFoundError: If no transaction, order, cart, mandate, or user
            exists for the given transaction_id -- these are all expected
            to exist together for any real transaction, so a missing one
            indicates data corruption rather than a normal not-found case,
            but is still reported as NotFoundError for a consistent API
            error shape.
    """
    transaction_row = await session.get(Transaction, transaction_id)
    if transaction_row is None:
        raise NotFoundError("TRANSACTION_NOT_FOUND", f"No transaction with id '{transaction_id}'.")

    order_row = await session.get(Order, transaction_row.order_id)
    if order_row is None:
        raise NotFoundError("ORDER_NOT_FOUND", f"No order with id '{transaction_row.order_id}'.")

    cart_row = await session.get(Cart, order_row.cart_id)
    if cart_row is None:
        raise NotFoundError("CART_NOT_FOUND", f"No cart with id '{order_row.cart_id}'.")
    cart_response = await to_cart_response(session, cart_row)

    mandate_row = await session.get(Mandate, order_row.mandate_id)
    if mandate_row is None:
        raise NotFoundError("MANDATE_NOT_FOUND", f"No mandate with id '{order_row.mandate_id}'.")
    signed_mandate = to_signed_mandate(mandate_row)

    buyer_row = await session.get(User, cart_row.user_id)
    if buyer_row is None:
        raise NotFoundError("USER_NOT_FOUND", f"No user with id '{cart_row.user_id}'.")

    # Filtered by mandate_id, not order_id: checkout_service.py's pre-order
    # events (HARD_POLICY_PASSED, CART_FROZEN, MERCHANT_PROPOSAL_CREATED,
    # INTENT_GATE_*, CART_REVALIDATION_*) are recorded before any Order row
    # exists, so they only ever carry mandate_id -- only later events
    # (RAZORPAY_ORDER_CREATED onward) also carry order_id. mandate_id is set
    # on every event throughout the whole flow, so it's the complete key.
    events_result = await session.execute(
        select(AuditEvent).where(AuditEvent.mandate_id == mandate_row.id).order_by(AuditEvent.sequence)
    )
    events = [
        TransactionTraceEvent(
            event_type=event.event_type,
            decision=event.decision,
            reason_code=event.reason_code,
            created_at=event.created_at,
        )
        for event in events_result.scalars().all()
    ]

    return TransactionTraceResponse(
        transaction=_to_transaction_response(transaction_row),
        order=OrderSummary(
            order_id=str(order_row.id),
            cart_id=str(order_row.cart_id),
            mandate_id=signed_mandate.payload.mandate_id,
            razorpay_order_id=order_row.razorpay_order_id,
            status=order_row.status,
            amount_minor=order_row.amount_minor,
            currency=order_row.currency,
        ),
        cart=cart_response,
        mandate=MandateSummary(
            mandate_id=signed_mandate.payload.mandate_id,
            product_type=signed_mandate.payload.intent.product_type,
            notes=signed_mandate.payload.intent.notes,
            max_amount_minor=signed_mandate.payload.max_amount,
            allowed_categories=signed_mandate.payload.allowed_categories,
            status=mandate_row.status.value,
        ),
        buyer=BuyerSummary(user_id=str(buyer_row.id), email=buyer_row.email, name=buyer_row.name),
        events=events,
    )
