"""
Purpose: Import every ORM model so app.db.base.Base.metadata is complete.

Alembic's env.py imports this module before autogenerating migrations;
without it, tables whose model files are never otherwise imported would be
silently missing from the generated schema.
"""
from app.db.models.audit_event import AuditEvent
from app.db.models.authorization_request import AuthorizationRequest
from app.db.models.cart import Cart
from app.db.models.cart_item import CartItem
from app.db.models.inventory import Inventory
from app.db.models.mandate import Mandate
from app.db.models.merchant import Merchant
from app.db.models.order import Order
from app.db.models.product import Product
from app.db.models.transaction import Transaction
from app.db.models.user import User

__all__ = [
    "AuditEvent",
    "AuthorizationRequest",
    "Cart",
    "CartItem",
    "Inventory",
    "Mandate",
    "Merchant",
    "Order",
    "Product",
    "Transaction",
    "User",
]
