"""
Purpose: ORM model for shopping carts.

`frozen_hash` is the SHA-256 hash computed by app.carts.freeze in Phase 3
when `request_checkout` freezes the cart. It is a separate artifact from the
mandate (plan.md Rule 4) — the mandate never embeds cart_hash, and this
model never embeds mandate content.

`mandate_id` (added in Phase 10, after the adversarial suite found a real
gap) records which mandate a cart was FROZEN under, once frozen. It exists
solely so app.policy.checks.check_mandate_not_reused_by_another_cart can
detect and block an ACTIVE-but-unpaid mandate being reused to freeze a
*second*, different cart -- single-use enforcement previously only applied
at payment capture (app.mandates.service.consume_mandate), leaving a window
where one mandate could authorize freezing multiple carts before any of
them was ever paid. Set once, at first freeze, by
app.services.checkout_service.request_checkout(); never set for an OPEN cart.

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
    # Set at first freeze only -- see module docstring. NULL for OPEN carts.
    mandate_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mandates.id"), nullable=True
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
