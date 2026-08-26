"""
Purpose: ORM model for AgentPay demo users.

A user is the authorization owner: the human on whose behalf Claude (the
external buyer agent) transacts, and whose signed mandate expresses their
actual spending/intent authorization (plan.md Section 8.1).
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class User(Base):
    """A demo user: the person who authorizes purchases via a signed mandate."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # Nullable: users created before the login page existed (e.g. via
    # POST /api/users, still used by Claude/MCP to resolve a user_id) have
    # no password yet. app.auth.service claims one for them on first login
    # -- see its docstring.
    password_hash: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
