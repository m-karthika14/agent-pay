"""
Purpose: Central catalog of AgentPay reason codes.

Every deterministic BLOCK/REJECT decision in AgentPay carries one of these
codes, so audit records, API error responses, and tests can all refer to the
same stable vocabulary instead of ad-hoc strings (plan.md Section 11.3).

Phase scope: mandate-verification, replay, and cart/policy-engine codes are
defined here (Phase 1 + Phase 3). Merchant-proposal codes
(PROPOSAL_INTENT_VIOLATION, etc.) are added in Phase 6/7 when the merchant
agent and intent gate exist. This file is extended in place as each phase
needs new codes — it is not reorganized or duplicated.
"""

# --- Mandate verification (Phase 1) ---
MANDATE_INVALID_SIGNATURE = "MANDATE_INVALID_SIGNATURE"
MANDATE_EXPIRED = "MANDATE_EXPIRED"
MANDATE_MERCHANT_MISMATCH = "MANDATE_MERCHANT_MISMATCH"
MANDATE_CATEGORY_FORBIDDEN = "MANDATE_CATEGORY_FORBIDDEN"
MANDATE_AMOUNT_EXCEEDED = "MANDATE_AMOUNT_EXCEEDED"
MANDATE_CURRENCY_MISMATCH = "MANDATE_CURRENCY_MISMATCH"
MANDATE_ALREADY_CONSUMED = "MANDATE_ALREADY_CONSUMED"

# --- Replay protection (Phase 1) ---
REPLAY_DETECTED = "REPLAY_DETECTED"

# --- Deterministic policy engine / cart integrity (Phase 3) ---
IDEMPOTENCY_DUPLICATE = "IDEMPOTENCY_DUPLICATE"
CART_HASH_MISMATCH = "CART_HASH_MISMATCH"
INVENTORY_INVALID = "INVENTORY_INVALID"

# --- Terminal transaction violations (Phase 3) ---
TRANSACTION_BLOCKED_HARD_POLICY = "TRANSACTION_BLOCKED_HARD_POLICY"
TRANSACTION_BLOCKED_POST_REVALIDATION = "TRANSACTION_BLOCKED_POST_REVALIDATION"

# --- Intent Gate outcomes (Phase 7) ---
# PROPOSAL_INTENT_VIOLATION and PROPOSAL_AMBIGUOUS_INTENT reflect the LLM's
# own classification (BLOCK / ESCALATE respectively). PROPOSAL_LOW_CONFIDENCE
# and PROPOSAL_GATEWAY_ERROR are assigned by app.intent.gate's deterministic
# wrapper -- never by the LLM itself -- so the reason-code vocabulary stays
# fixed regardless of what free-text the model returns (plan.md Section 11.3).
PROPOSAL_INTENT_VIOLATION = "PROPOSAL_INTENT_VIOLATION"
PROPOSAL_AMBIGUOUS_INTENT = "PROPOSAL_AMBIGUOUS_INTENT"
PROPOSAL_LOW_CONFIDENCE = "PROPOSAL_LOW_CONFIDENCE"
PROPOSAL_GATEWAY_ERROR = "PROPOSAL_GATEWAY_ERROR"

# --- Mandate reuse across carts (Phase 10) ---
# Found by the adversarial suite (eval/scenarios.json's cap_splitting
# cases): single-use enforcement previously only applied at payment capture
# (app.mandates.service.consume_mandate), leaving a window where one
# ACTIVE-but-unpaid mandate could freeze a *second*, different cart. This
# code is for app.policy.checks.check_mandate_not_reused_by_another_cart,
# which closes that window at request_checkout() time instead.
MANDATE_ALREADY_ASSOCIATED_WITH_ANOTHER_CART = "MANDATE_ALREADY_ASSOCIATED_WITH_ANOTHER_CART"

# --- User-set AI Shopping Budget (Phase 4) ---
# A user's own, independently-set spending ceiling (app.budgets.service),
# checked in app.authorization.service.create_authorization_request() (what
# Claude asks for) AND approve_authorization_request() (what a human's Edit
# ends up submitting) -- defense in depth, so the budget is a hard ceiling
# regardless of which side would otherwise push a number above it.
EXCEEDS_AI_SHOPPING_BUDGET = "EXCEEDS_AI_SHOPPING_BUDGET"

# --- Automatic Payments (Phase 5) ---
# A user's own "Automatic Payments" authorization (app.db.models.
# payment_authorization.PaymentAuthorization) is a SEPARATE concept from the
# AI Shopping Budget/Mandate -- these codes are checked by
# app.payments.authorization_service.execute_authorized_payment(), which only
# ever runs AFTER every existing mandate/policy/Intent Gate check has already
# passed and the cart is FROZEN (plan.md's "AI authority AND payment
# authority, both required" rule).
PAYMENT_AUTHORIZATION_REQUIRED = "PAYMENT_AUTHORIZATION_REQUIRED"
PAYMENT_AUTHORIZATION_INVALID = "PAYMENT_AUTHORIZATION_INVALID"
PAYMENT_BLOCKED_BUDGET_EXCEEDED = "PAYMENT_BLOCKED_BUDGET_EXCEEDED"
# The payment provider (Razorpay) rejected an Automatic Payments setup
# request -- e.g. the account lacks recurring card payments, or the
# registration order payload was refused. A real, surfaced failure: the
# frontend shows the provider's reason rather than a generic 500.
PAYMENT_AUTHORIZATION_SETUP_FAILED = "PAYMENT_AUTHORIZATION_SETUP_FAILED"

# --- Cart-owned mandate resolution (Phase 2.1) ---
# request_checkout() can be called with no mandate_id, resolving it from the
# cart's own state (already-frozen -> its recorded mandate; still OPEN -> the
# most recent APPROVED app.db.models.authorization_request.AuthorizationRequest
# for that cart). This code fires only when neither source has one.
NO_APPROVED_AUTHORIZATION = "NO_APPROVED_AUTHORIZATION"
