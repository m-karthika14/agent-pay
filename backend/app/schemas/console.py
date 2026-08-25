"""
Purpose: Pydantic schemas for the Merchant Console's aggregate/overview API
(plan.md Section 18 — Evaluation/console, Section 19.2 "Revenue at risk /
basket metrics").
"""
from datetime import datetime

from pydantic import BaseModel


class RecentTransactionSummary(BaseModel):
    """One row in the console's recent-activity list."""

    transaction_id: str
    order_id: str
    status: str
    amount_minor: int
    currency: str
    created_at: datetime


class ConsoleSummaryResponse(BaseModel):
    """
    Merchant-wide aggregate counts, for the console's overview panel
    (plan.md Section 19.2 "Revenue at risk / basket metrics").

    Counts only -- no fabricated figures. transaction_count_by_status keys
    are whatever status strings actually exist on Transaction rows (e.g.
    "PENDING", "CAPTURED", "FAILED"), so the panel never silently omits or
    invents a status.
    """

    total_transactions: int
    transaction_count_by_status: dict[str, int]
    total_mandates: int
    total_audit_events: int
    recent_transactions: list[RecentTransactionSummary]


class ConsoleMetricsResponse(BaseModel):
    """
    The Phase 10 evaluation results (Mandate Ceiling Drift, abandonment,
    escalation, adversarial suite), for the console's evidence panel
    (plan.md Section 19.2 "Revenue at risk" / Section 30 Slide 7).

    available=False (with metrics=None) means eval/metrics.py has not been
    run yet for this environment -- the console must show that plainly
    rather than a blank or fabricated chart (plan.md Section 31: never
    invent evaluation numbers).
    """

    available: bool
    metrics: dict | None = None
