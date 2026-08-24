"""
Purpose: Pydantic schemas for Razorpay checkout sessions, transactions, and
transaction traces (plan.md Section 16, Section 18).
"""
from datetime import datetime

from pydantic import BaseModel


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


class TransactionTraceResponse(BaseModel):
    """A transaction's full ordered decision trace, for the merchant console / debugging."""

    transaction: TransactionResponse
    events: list[TransactionTraceEvent]
