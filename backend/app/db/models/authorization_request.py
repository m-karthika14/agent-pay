"""
Purpose: ORM model for Claude-initiated authorization requests.

A row here is Claude's *ask* -- proposed spending terms for a cart it has
already created, before any mandate exists. It is never itself spending
authority: approving one (app.authorization.service.approve_authorization_request)
creates a real, signed Mandate through the exact same signing path
app.mandates.service.create_mandate_from_request already uses for a human
authorizing directly via /authorize-agent. Claude can create/poll these rows
via MCP, but can never move a row to APPROVED itself.

user_id/merchant_id are deliberately not duplicated onto this table -- both
are always reachable by joining through Cart, matching how ProductResponse's
merchant_name/merchant_slug are computed at read time rather than stored.
"""
import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AuthorizationRequestStatus(StrEnum):
    """Lifecycle state of an authorization request."""

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class AuthorizationRequest(Base):
    """Claude's proposed spending terms for a cart, awaiting a human's Reject/Edit/Approve."""

    __tablename__ = "authorization_requests"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    cart_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("carts.id"), nullable=False)
    status: Mapped[AuthorizationRequestStatus] = mapped_column(
        Enum(AuthorizationRequestStatus, name="authorization_request_status"),
        nullable=False,
        default=AuthorizationRequestStatus.PENDING,
    )
    max_amount_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    allowed_categories: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    allow_addons: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    delivery_requirement: Mapped[str] = mapped_column(String(50), nullable=False, default="under_3_days")
    single_use: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    expires_in_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=24)
    product_type: Mapped[str] = mapped_column(String(200), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Claude's own natural-language justification for the ask (e.g. "matches
    # your request for wireless earbuds under 2,500"), shown as-is in the
    # human's approval popup.
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Set only once approved -- the real, signed mandate this request
    # produced via app.mandates.service.create_mandate_from_request.
    resulting_mandate_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mandates.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
