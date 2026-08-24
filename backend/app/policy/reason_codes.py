"""
Purpose: Central catalog of AgentPay reason codes.

Every deterministic BLOCK/REJECT decision in AgentPay carries one of these
codes, so audit records, API error responses, and tests can all refer to the
same stable vocabulary instead of ad-hoc strings (plan.md Section 11.3).

Phase scope: only mandate-verification and replay codes are defined here so
far (Phase 1 — Security Foundation). Cart-integrity codes (CART_HASH_MISMATCH,
INVENTORY_INVALID, IDEMPOTENCY_DUPLICATE) are added in Phase 3 when the
deterministic policy engine is built; merchant-proposal codes
(PROPOSAL_INTENT_VIOLATION, etc.) in Phase 6/7; transaction-block codes in
Phase 3/8. This file is extended in place as each phase needs new codes — it
is not reorganized or duplicated.
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
