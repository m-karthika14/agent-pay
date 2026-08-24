"""
Purpose: ORM model for payment transactions against an order.

`idempotency_key` is unique so a duplicated payment-affecting request (e.g.
a retried POST /api/checkout/{cart_id}/complete) can never create a second
transaction/order for the same logical request (plan.md Section 24.2).

`razorpay_event_id` is unique and records the most recent Razorpay webhook
event that updated this row, used to reject duplicate webhook deliveries
(plan.md Section 16.4 / Section 24.3). Scope note: this project's webhook
scope is limited to the two terminal payment events (payment.captured,
payment.failed) per transaction, so "last event id on the row" is
sufficient dedup for this project -- a system tracking many event types per
transaction would need a separate append-only event log instead. Per
plan.md Section 16.4, heavier webhook-event infrastructure (e.g. a durable
queue) is explicitly out of scope for this hackathon.
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Transaction(Base):
    """A payment attempt/result against an order."""

    __tablename__ = "transactions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("orders.id"), nullable=False)
    razorpay_payment_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    razorpay_signature: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="PENDING")
    idempotency_key: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    razorpay_event_id: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    failure_message: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
