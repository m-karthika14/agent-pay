"""
Purpose: Verify app.payments.signatures against the documented Razorpay
HMAC-SHA256 algorithm (plan.md Section 16.3), using a locally-known test
secret rather than a live Razorpay account -- these are pure crypto checks.
"""
import hashlib
import hmac

import pytest

from app.core.config import get_settings
from app.payments.signatures import verify_payment_signature, verify_webhook_signature


@pytest.fixture
def razorpay_test_secrets(monkeypatch):
    """Configure known Test Mode-shaped secrets for the duration of one test."""
    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test_fake_key_id")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "fake_key_secret_for_tests")
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", "fake_webhook_secret_for_tests")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _sign(secret: str, message: str) -> str:
    return hmac.new(key=secret.encode("utf-8"), msg=message.encode("utf-8"), digestmod=hashlib.sha256).hexdigest()


def test_valid_payment_signature_is_accepted(razorpay_test_secrets) -> None:
    order_id, payment_id = "order_test123", "pay_test456"
    signature = _sign("fake_key_secret_for_tests", f"{order_id}|{payment_id}")

    assert verify_payment_signature(order_id, payment_id, signature) is True


def test_tampered_payment_id_is_rejected(razorpay_test_secrets) -> None:
    order_id = "order_test123"
    signature = _sign("fake_key_secret_for_tests", f"{order_id}|pay_test456")

    assert verify_payment_signature(order_id, "pay_DIFFERENT", signature) is False


def test_payment_signature_from_wrong_secret_is_rejected(razorpay_test_secrets) -> None:
    order_id, payment_id = "order_test123", "pay_test456"
    signature = _sign("wrong_secret", f"{order_id}|{payment_id}")

    assert verify_payment_signature(order_id, payment_id, signature) is False


def test_valid_webhook_signature_is_accepted(razorpay_test_secrets) -> None:
    body = b'{"event":"payment.captured","payload":{}}'
    signature = _sign("fake_webhook_secret_for_tests", body.decode("utf-8"))

    assert verify_webhook_signature(body, signature) is True


def test_tampered_webhook_body_is_rejected(razorpay_test_secrets) -> None:
    original_body = b'{"event":"payment.captured","payload":{}}'
    signature = _sign("fake_webhook_secret_for_tests", original_body.decode("utf-8"))

    tampered_body = b'{"event":"payment.captured","payload":{"tampered":true}}'

    assert verify_webhook_signature(tampered_body, signature) is False


def test_webhook_signature_from_wrong_secret_is_rejected(razorpay_test_secrets) -> None:
    body = b'{"event":"payment.captured","payload":{}}'
    signature = _sign("some_other_secret", body.decode("utf-8"))

    assert verify_webhook_signature(body, signature) is False
