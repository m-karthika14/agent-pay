"""
Purpose: Shared SQLAlchemy declarative base for all AgentPay ORM models.

Every model in app.db.models inherits from this Base so Alembic's
autogenerate and Base.metadata.create_all() can discover the full schema
from a single import.
"""
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base class for all AgentPay database models."""
