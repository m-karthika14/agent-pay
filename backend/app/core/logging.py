"""
Purpose: Configure structured application logging.

Per plan.md Section 48: log safe identifiers (request_id, transaction_id,
mandate_id, order_id, reason_code) and never log secrets, private keys, or
full payment credentials. This module only configures the stdlib logging
format; individual call sites are responsible for what they choose to log.
"""
import logging


def configure_logging(level: str = "INFO") -> None:
    """
    Configure root logging with a consistent, timestamped format.

    Args:
        level: Logging level name (e.g. "INFO", "DEBUG"). Invalid values
            fall back to INFO rather than raising, since logging setup
            should never be able to crash application startup.
    """
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
