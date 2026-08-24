"""
Purpose: ORM model for shopping carts.

`frozen_hash` is the SHA-256 hash computed by app.carts.freeze in Phase 3
when `request_checkout` freezes the cart. It is a separate artifact from the
mandate (plan.md Rule 4) — carts and mandates are linked only through a
checkout/order, never by embedding one inside the other.

Cart business logic (create/add-item/freeze) is built in Phase 2/3; this
model only defines the schema needed now for Phase 1's PostgreSQL setup.
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Cart(Base):
    """A buyer's shopping cart with a merchant, mutable until frozen at checkout."""

    __tablename__ = "carts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    merchant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("merchants.id"), nullable=False
    )
    # e.g. "OPEN" or "FROZEN" (plan.md Section 10.3/10.4). Modeled as a plain
    # string here since the cart status lifecycle is defined in Phase 2/3.
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="OPEN")
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    subtotal_minor: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    frozen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    frozen_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
