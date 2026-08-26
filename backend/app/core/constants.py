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

# UrbanNest is a single small demo merchant with one uniform delivery/return
# policy (plan.md Section 18) — these are not per-product database columns.
DEFAULT_DELIVERY_POLICY = "Delivery within 3 days"
DEFAULT_RETURN_POLICY = "7-day returns"

# Cart lifecycle states (plan.md Section 10.3/10.4). Cart.status is a plain
# string column (business rules for the lifecycle live here, not in the DB).
CART_STATUS_OPEN = "OPEN"
CART_STATUS_FROZEN = "FROZEN"

# The real demo merchants (plan.md Section 18 / scripts/seed_database.py).
# app.catalog.service's catalog listing filters to exactly these merchants
# (when no specific one is requested) so the storefront/MCP catalog never
# picks up throwaway merchants the test suite creates (each integration test
# creates its own isolated merchant+product fixtures, independent of these
# seeded ones -- see tests/integration/*.py's `_create_fixture_data()`
# helpers).
URBANNEST_SLUG = "urbannest"
TECHHUB_SLUG = "techhub"
DEMO_MERCHANT_SLUGS = (URBANNEST_SLUG, TECHHUB_SLUG)
