"""
Purpose: ORM model for signed AgentPay mandates.

Stores the signed payload and signature as persisted, opaque artifacts
(`signed_payload` is the canonical JSON produced by
app.security.canonical.canonicalize_mandate, stored for audit/replay
purposes; verification always re-derives trust from the signature, never
from trusting this row's contents blindly).

Per plan.md Rule 4, `cart_hash` must NEVER be added to this model — the cart
is a separate artifact, frozen and hashed later at checkout time.
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.schemas.mandate import MandateStatus


class Mandate(Base):
    """A signed mandate: the user's persisted spending/intent authorization."""

    __tablename__ = "mandates"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    # Business-facing mandate identifier (e.g. "M-001"), distinct from the
    # internal UUID primary key.
    mandate_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    merchant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("merchants.id"), nullable=False
    )
    # Canonical JSON bytes (as text) of the MandatePayload that was signed.
    signed_payload: Mapped[str] = mapped_column(Text, nullable=False)
    signature: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[MandateStatus] = mapped_column(
        Enum(MandateStatus, name="mandate_status"), nullable=False, default=MandateStatus.ACTIVE
    )
    single_use: Mapped[bool] = mapped_column(Boolean, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
