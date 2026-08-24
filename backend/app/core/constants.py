"""
Purpose: Named constants for values that would otherwise be unexplained magic
numbers in business logic (plan.md Section 5.6).

Only constants actually used by the current phase are defined here; more are
added as later phases need them.
"""

# Maximum number of upsell/cross-sell proposals the Merchant Revenue Agent may
# submit for a single cart before the original cart is retained (plan.md Rule 7).
MAX_MERCHANT_PROPOSALS = 3

# Default confidence threshold below which the intent gate must fail closed
# and escalate rather than allow (plan.md Section 14.4). This is a fallback;
# the real value used at runtime comes from Settings.intent_confidence_threshold
# once it is calibrated and frozen in Phase 7.
DEFAULT_INTENT_THRESHOLD = 0.80

# Hash algorithm used for cart freezing and the audit hash chain
# (plan.md Section 3.6 / Section 23.2).
AUDIT_HASH_ALGORITHM = "sha256"
