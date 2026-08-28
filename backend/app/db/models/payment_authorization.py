"""
Purpose: ORM model for a user's own "Automatic Payments" authorization --
HOW AgentPay is permitted to pay, as distinct from the existing Mandate
(WHAT the AI is allowed to buy) and the AI Shopping Budget (WHAT ceiling
Claude's own asks are held to).

A row here never stores raw card/UPI/bank credentials -- only the Razorpay-
side references (`razorpay_customer_id`, `razorpay_token_id`) needed to
invoke Razorpay's own Recurring Payments API later
(app.payments.razorpay_client.create_recurring_payment), exactly the
provider-side identifier pattern plan.md's "Secret rules" already use for
the mandate's signed_payload/signature (opaque artifacts, never raw
credentials).
"""
import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PaymentAuthorizationStatus(StrEnum):
    """Lifecycle state of a payment authorization."""

    # Setup started (Razorpay Customer + registration Order created) but the
    # ONE interactive Checkout step hasn't been confirmed as successful yet
    # -- never treated as usable authority; execute_authorized_payment()
    # only ever considers ACTIVE. Exists so setup state survives a browser
    # refresh/multi-device flow instead of being trusted back from the
    # frontend at confirm time.
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"
    FAILED = "FAILED"


class PaymentAuthorization(Base):
    """
    A user's authorized automatic-payment method (Razorpay Recurring
    Payments token), used by AgentPay to execute an already-authorized AI
    purchase without a manual "Pay" step -- never by Claude or the Merchant
    Agent directly (app.payments.authorization_service is the only writer).
    """

    __tablename__ = "payment_authorizations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False, default="razorpay")
    # Razorpay-side references only -- never a raw card/UPI/bank credential.
    razorpay_customer_id: Mapped[str] = mapped_column(String(100), nullable=False)
    razorpay_token_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # The Razorpay order used for the ONE interactive registration
    # transaction -- kept so confirm_payment_authorization() can verify the
    # callback's razorpay_payment_id actually belongs to the order this
    # service itself created, never trusting the frontend's say-so alone.
    setup_razorpay_order_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[PaymentAuthorizationStatus] = mapped_column(
        Enum(PaymentAuthorizationStatus, name="payment_authorization_status"),
        nullable=False,
        default=PaymentAuthorizationStatus.ACTIVE,
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")
    # The ceiling this specific payment authorization itself permits per
    # transaction -- separate from (and checked in addition to) the AI
    # Shopping Budget; registered with Razorpay as the token's own max_amount.
    max_amount_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    authorized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
