"""
Purpose: Aggregate/overview read logic for the Merchant Console (plan.md
Section 18 `GET /api/console/*`, Section 19.2).

Pure read-only queries plus (for get_metrics) reading the JSON report
eval/metrics.py already wrote to disk -- this module never recomputes
evaluation numbers itself, since eval/ is the single source of truth for
those (plan.md Section 31: never invent evaluation numbers).
"""
import json
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.audit_event import AuditEvent
from app.db.models.cart import Cart
from app.db.models.mandate import Mandate
from app.db.models.merchant import Merchant
from app.db.models.order import Order
from app.db.models.transaction import Transaction
from app.schemas.console import ConsoleMetricsResponse, ConsoleSummaryResponse, RecentTransactionSummary

# eval/reports/metrics_summary.json, resolved relative to this file
# (backend/app/services/console_service.py -> repo root -> eval/reports/).
_METRICS_REPORT_PATH = Path(__file__).resolve().parents[3] / "eval" / "reports" / "metrics_summary.json"


async def get_summary(session: AsyncSession) -> ConsoleSummaryResponse:
    """
    Build the console's overview panel: aggregate counts plus the most
    recent transactions.

    Args:
        session: Active AsyncSession.

    Returns:
        ConsoleSummaryResponse.
    """
    status_counts_result = await session.execute(
        select(Transaction.status, func.count()).group_by(Transaction.status)
    )
    transaction_count_by_status = {status: count for status, count in status_counts_result.all()}
    total_transactions = sum(transaction_count_by_status.values())

    total_mandates_result = await session.execute(select(func.count()).select_from(Mandate))
    total_mandates = total_mandates_result.scalar_one()

    total_events_result = await session.execute(select(func.count()).select_from(AuditEvent))
    total_audit_events = total_events_result.scalar_one()

    recent_result = await session.execute(
        select(Transaction, Order, Merchant)
        .join(Order, Order.id == Transaction.order_id)
        .join(Cart, Cart.id == Order.cart_id)
        .join(Merchant, Merchant.id == Cart.merchant_id)
        .order_by(Transaction.created_at.desc())
        .limit(10)
    )
    recent_transactions = [
        RecentTransactionSummary(
            transaction_id=str(transaction.id),
            order_id=str(order.id),
            status=transaction.status,
            amount_minor=order.amount_minor,
            currency=order.currency,
            merchant_name=merchant.name,
            merchant_slug=merchant.slug,
            created_at=transaction.created_at,
        )
        for transaction, order, merchant in recent_result.all()
    ]

    return ConsoleSummaryResponse(
        total_transactions=total_transactions,
        transaction_count_by_status=transaction_count_by_status,
        total_mandates=total_mandates,
        total_audit_events=total_audit_events,
        recent_transactions=recent_transactions,
    )


def get_metrics() -> ConsoleMetricsResponse:
    """
    Read the Phase 10 evaluation report from disk, if it has been run.

    Returns:
        ConsoleMetricsResponse with available=True and the parsed report,
        or available=False if eval/metrics.py has never been run in this
        environment (no report file exists yet).
    """
    if not _METRICS_REPORT_PATH.exists():
        return ConsoleMetricsResponse(available=False, metrics=None)
    with open(_METRICS_REPORT_PATH, encoding="utf-8") as f:
        return ConsoleMetricsResponse(available=True, metrics=json.load(f))
