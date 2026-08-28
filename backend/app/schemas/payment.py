"""
Purpose: Pydantic schemas for Razorpay checkout sessions, transactions, and
transaction traces (plan.md Section 16, Section 18).
"""
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.cart import CartResponse


class CheckoutSessionResponse(BaseModel):
    """
    Everything the (future) frontend needs to open Razorpay Standard
    Checkout for a frozen cart -- and nothing else. `razorpay_key_id` is
    the public Test Mode Key ID; the Key Secret is never included here
    (plan.md Section 6 "Secret rules").
    """

    order_id: str
    razorpay_order_id: str
    razorpay_key_id: str
    amount_minor: int
    currency: str
    #: Set only when this call also attempted Automatic Payments (plan.md
    #: Phase 5) -- None means "no active payment authorization, proceed
    #: with the existing manual Razorpay Checkout exactly as before."
    #: "CAPTURED" means the order is already genuinely paid -- the caller
    #: (browser or Claude via MCP) never needs to open Checkout at all.
    #: "REQUIRES_AUTHENTICATION"/"FAILED"/"INVALID" all mean automatic
    #: payment did not complete and the existing manual flow is the
    #: safe fallback -- never a false success.
    auto_payment_status: str | None = None


class TransactionResponse(BaseModel):
    """A single payment transaction against an order."""

    transaction_id: str
    order_id: str
    razorpay_payment_id: str | None
    status: str
    failure_code: str | None
    failure_message: str | None
    created_at: datetime
    updated_at: datetime


class TransactionTraceEvent(BaseModel):
    """One audit event in a transaction's decision trace (plan.md Section 18 — trace)."""

    event_type: str
    decision: str | None
    reason_code: str | None
    created_at: datetime


class OrderSummary(BaseModel):
    """The order linking a transaction back to its authorizing cart and mandate."""

    order_id: str
    cart_id: str
    mandate_id: str = Field(description='Business-facing mandate_id (e.g. "M-001").')
    razorpay_order_id: str | None
    status: str
    amount_minor: int
    currency: str


class MandateSummary(BaseModel):
    """
    The signed mandate that authorized this transaction, decoded from its
    persisted signed_payload (plan.md Section 24 "signed mandate" panel).

    Unlike audit event payloads (only their hash is persisted, by design --
    see app.audit.service), a mandate's full canonical payload IS persisted
    (app.db.models.mandate.Mandate.signed_payload) precisely so it can be
    reconstructed and displayed later; this is not a departure from the
    Phase 1 audit-privacy design, just a different, already-existing artifact.
    """

    mandate_id: str
    product_type: str
    notes: str | None
    max_amount_minor: int
    allowed_categories: list[str]
    status: str


class BuyerSummary(BaseModel):
    """The user who authorized this transaction (plan.md Section 24 "buyer" panel)."""

    user_id: str
    email: str
    name: str


class OrderHistoryEntry(BaseModel):
    """
    One row in a buyer's order history (storefront "Buying History" tab).

    Deliberately lighter than TransactionTraceResponse -- a list view needs
    a short item summary and the order's own status, not the full decision
    trace of any single order.
    """

    order_id: str
    mandate_id: str = Field(description='Business-facing mandate_id (e.g. "M-001").')
    status: str = Field(description='Order.status: "CREATED", "PAID", or "PAYMENT_FAILED".')
    amount_minor: int
    currency: str
    item_summary: str = Field(description='e.g. "2x Wireless Earbuds, 1x Protective Earbuds Case".')
    created_at: datetime


class TransactionTraceResponse(BaseModel):
    """
    A transaction's full ordered decision trace plus enough context (order,
    cart, mandate, buyer) to render the Merchant Console's Transaction view
    (plan.md Section 19.2/24) from a single call.

    Scope note: `events` carries event_type/decision/reason_code -- exactly
    what's actually persisted (plan.md Section 1's Phase 1 audit design
    stores only a payload_hash, not the raw payload, so a merchant
    proposal's exact free-text reason or amount can't be recovered here for
    a past transaction). `cart` shows the transaction's actual final,
    frozen item list instead, which IS fully persisted and accurate.
    """

    transaction: TransactionResponse
    order: OrderSummary
    cart: CartResponse
    mandate: MandateSummary
    buyer: BuyerSummary
    events: list[TransactionTraceEvent]
