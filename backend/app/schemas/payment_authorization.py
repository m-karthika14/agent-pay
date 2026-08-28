"""
Purpose: Pydantic schemas for a user's "Automatic Payments" authorization --
HOW AgentPay is permitted to pay, kept deliberately separate from the AI
Shopping Budget (WHAT ceiling Claude's own asks are held to,
app.schemas.budget) and from the shopping Mandate (WHAT the AI is allowed to
buy). A transaction needs BOTH a valid mandate/budget AND an active payment
authorization before AgentPay may execute payment automatically.
"""
from datetime import datetime

from pydantic import BaseModel, Field


class SetupPaymentAuthorizationRequest(BaseModel):
    """Request body for POST /api/users/{user_id}/payment-authorization -- starts the ONE interactive setup step."""

    max_amount_minor: int = Field(gt=0, description="The per-transaction ceiling this payment method may be used for.")
    currency: str = Field(default="INR")


class SetupPaymentAuthorizationResponse(BaseModel):
    """
    Everything the frontend needs to open Razorpay Checkout for the single
    interactive registration transaction -- mirrors CheckoutSessionResponse's
    shape/purpose exactly (public key id + order id, never a secret).
    """

    razorpay_order_id: str
    razorpay_key_id: str
    razorpay_customer_id: str
    amount_minor: int
    currency: str


class ConfirmPaymentAuthorizationRequest(BaseModel):
    """
    Request body for POST /api/users/{user_id}/payment-authorization/confirm,
    sent once the user's browser completes the ONE interactive Razorpay
    Checkout step for registration. `razorpay_payment_id` is never trusted at
    face value -- the backend fetches it directly from Razorpay to verify it
    genuinely succeeded and belongs to the order this service itself created.
    """

    razorpay_order_id: str
    razorpay_payment_id: str


class PaymentAuthorizationResponse(BaseModel):
    """
    A user's current Automatic Payments authorization -- deliberately never
    includes razorpay_customer_id/razorpay_token_id (provider-side
    references, not secrets, but still not the frontend's business per
    plan.md Section 6 "Secret rules" precedent).
    """

    is_active: bool
    status: str | None = None
    provider: str | None = None
    currency: str | None = None
    max_amount_minor: int | None = None
    authorized_at: datetime | None = None
    expires_at: datetime | None = None
