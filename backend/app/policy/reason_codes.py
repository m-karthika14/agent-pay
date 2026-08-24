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
