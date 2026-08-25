"""
Purpose: Integration tests for Phase 8 -- the Merchant Revenue Agent and
Intent Gate wired into checkout_service.request_checkout() (plan.md Section
15 steps 9-13), exercised against a real database with both Gemini call
sites mocked (app.agents.merchant.nodes.classify_with_schema and
app.intent.gate.classify_with_schema) -- no live GEMINI_API_KEY required.

Mirrors tests/unit/test_merchant_agent.py's fixture pattern but goes one
layer up: calls checkout_service.request_checkout() directly (not
run_merchant_agent()), so these tests exercise the full step 9-13
orchestration, including cart mutation, re-freezing, and final
re-validation.
"""
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

from app.agents.merchant.nodes import _CandidateProposal, _CandidateProposalList
from app.ai.errors import GeminiUnavailableError
from app.carts.service import add_cart_item, create_cart
from app.db.models.inventory import Inventory
from app.db.models.merchant import Merchant
from app.db.models.product import Product
from app.db.models.user import User
from app.db.session import get_session_factory
from app.intent.models import IntentDecisionType, _IntentClassification
from app.mandates.service import create_mandate
from app.policy import reason_codes
from app.schemas.mandate import MandateIntent, MandatePayload
from app.schemas.proposal import ProposalStatus
from app.services.checkout_service import request_checkout

MERCHANT_PATCH_TARGET = "app.agents.merchant.nodes.classify_with_schema"
INTENT_PATCH_TARGET = "app.intent.gate.classify_with_schema"


async def _build_fixture() -> dict:
    """
    Create an isolated merchant, user, mandate, and an OPEN cart containing
    one electronics item, plus an extra in-stock electronics candidate
    product for the merchant agent to propose.
    """
    factory = get_session_factory()
    unique = uuid.uuid4().hex[:8]
    async with factory() as session:
        merchant = Merchant(slug=f"checkout-advisory-{unique}", name="Advisory Test Merchant", currency="INR")
        user = User(email=f"advisory-{unique}@agentpay.test", name="Advisory Test User")
        session.add_all([merchant, user])
        await session.flush()

        cart_product = Product(
            merchant_id=merchant.id, sku=f"CART-{unique}", name="Cart Item", description="d",
            price_minor=100_000, currency="INR", category="electronics", is_active=True,
        )
        candidate = Product(
            merchant_id=merchant.id, sku=f"CANDIDATE-{unique}", name="Candidate Upsell", description="d",
            price_minor=50_000, currency="INR", category="electronics", is_active=True,
        )
        session.add_all([cart_product, candidate])
        await session.flush()
        session.add_all(
            [
                Inventory(product_id=cart_product.id, quantity=10),
                Inventory(product_id=candidate.id, quantity=10),
            ]
        )
        await session.commit()

        payload = MandatePayload(
            mandate_id=f"M-advisory-{unique}",
            merchant_id=str(merchant.id),
            currency="INR",
            max_amount=500_000,
            allowed_categories=["electronics"],
            allow_addons=True,
            delivery_requirement="under_3_days",
            single_use=True,
            expires_at=datetime.now(UTC) + timedelta(days=1),
            intent=MandateIntent(product_type="test widget", notes="open to add-ons"),
        )
        await create_mandate(session, payload, user.id, merchant.id)
        await session.commit()

        cart = await create_cart(session, user.id, merchant.id, "INR")
        await add_cart_item(session, uuid.UUID(cart.cart_id), cart_product.id, 1)
        await session.commit()

        return {
            "cart_id": uuid.UUID(cart.cart_id),
            "mandate_id": payload.mandate_id,
            "candidate_id": str(candidate.id),
            "original_subtotal": 100_000,
            "candidate_price": 50_000,
        }


def _merchant_candidates(product_id: str, value: int = 50_000) -> _CandidateProposalList:
    return _CandidateProposalList(
        candidates=[
            _CandidateProposal(
                product_id=product_id, quantity=1, reason="Great add-on.", estimated_value_add_minor=value
            )
        ]
    )


def _intent_classification(decision: IntentDecisionType, confidence: float = 0.95) -> _IntentClassification:
    return _IntentClassification(decision=decision, confidence=confidence, reason="test reason")


async def test_no_candidates_leaves_cart_untouched() -> None:
    """When the merchant agent has nothing to propose, checkout proceeds with the original cart, untouched."""
    fixture = await _build_fixture()
    factory = get_session_factory()
    async with factory() as session:
        with patch(MERCHANT_PATCH_TARGET, new=AsyncMock(return_value=_CandidateProposalList(candidates=[]))):
            result = await request_checkout(session, fixture["cart_id"], fixture["mandate_id"])
        await session.commit()

    assert result.proposal.status in (ProposalStatus.NO_PROPOSAL, ProposalStatus.ORIGINAL_CART_RETAINED)
    assert result.cart.subtotal_minor == fixture["original_subtotal"]


async def test_cap_only_arm_auto_applies_proposal_without_consulting_intent_gate() -> None:
    """
    intent_gate_enabled=False (the Cap-only eval arm, plan.md Section 19.1)
    applies a hard-check-passed proposal directly -- the Intent Gate's
    Gemini call is never even patched here, so if the code tried to call it
    unmocked, this test would either hit real Gemini or hang/error; it
    doesn't, proving the gate is genuinely skipped, not just given a
    favorable mock.
    """
    fixture = await _build_fixture()
    factory = get_session_factory()
    async with factory() as session:
        with (
            patch(MERCHANT_PATCH_TARGET, new=AsyncMock(return_value=_merchant_candidates(fixture["candidate_id"]))),
            patch(INTENT_PATCH_TARGET, new=AsyncMock(side_effect=AssertionError("Intent Gate must not be called"))),
        ):
            result = await request_checkout(
                session, fixture["cart_id"], fixture["mandate_id"], intent_gate_enabled=False
            )
        await session.commit()

    assert result.proposal.status == ProposalStatus.PROPOSAL_ALLOWED
    assert result.proposal.product_id == fixture["candidate_id"]
    assert result.proposal.intent_confidence is None
    expected_total = fixture["original_subtotal"] + fixture["candidate_price"]
    assert result.cart.subtotal_minor == expected_total


async def test_intent_gate_allow_applies_proposal_and_reflects_new_total() -> None:
    """An Intent-Gate-ALLOWed proposal is applied to the cart and the new subtotal/hash reflect it."""
    fixture = await _build_fixture()
    factory = get_session_factory()
    async with factory() as session:
        with (
            patch(MERCHANT_PATCH_TARGET, new=AsyncMock(return_value=_merchant_candidates(fixture["candidate_id"]))),
            patch(INTENT_PATCH_TARGET, new=AsyncMock(return_value=_intent_classification(IntentDecisionType.ALLOW))),
        ):
            result = await request_checkout(session, fixture["cart_id"], fixture["mandate_id"])
        await session.commit()

    assert result.proposal.status == ProposalStatus.PROPOSAL_ALLOWED
    assert result.proposal.product_id == fixture["candidate_id"]
    expected_total = fixture["original_subtotal"] + fixture["candidate_price"]
    assert result.cart.subtotal_minor == expected_total
    assert len(result.cart.items) == 2
    assert result.frozen_hash == result.cart.frozen_hash


async def test_intent_gate_block_leaves_original_cart_and_is_non_terminal() -> None:
    """An Intent-Gate-BLOCKed proposal is discarded; the original cart still completes checkout normally."""
    fixture = await _build_fixture()
    factory = get_session_factory()
    async with factory() as session:
        with (
            patch(MERCHANT_PATCH_TARGET, new=AsyncMock(return_value=_merchant_candidates(fixture["candidate_id"]))),
            patch(INTENT_PATCH_TARGET, new=AsyncMock(return_value=_intent_classification(IntentDecisionType.BLOCK))),
        ):
            result = await request_checkout(session, fixture["cart_id"], fixture["mandate_id"])
        await session.commit()

    assert result.proposal.status == ProposalStatus.PROPOSAL_REJECTED
    assert result.proposal.reason_code == reason_codes.PROPOSAL_INTENT_VIOLATION
    assert result.cart.subtotal_minor == fixture["original_subtotal"]
    assert len(result.cart.items) == 1


async def test_low_confidence_intent_decision_escalates_and_is_non_terminal() -> None:
    """An ambiguous/low-confidence Intent Gate verdict escalates but still lets the original cart complete checkout."""
    fixture = await _build_fixture()
    factory = get_session_factory()
    async with factory() as session:
        with (
            patch(MERCHANT_PATCH_TARGET, new=AsyncMock(return_value=_merchant_candidates(fixture["candidate_id"]))),
            patch(
                INTENT_PATCH_TARGET,
                new=AsyncMock(return_value=_intent_classification(IntentDecisionType.ALLOW, confidence=0.10)),
            ),
        ):
            result = await request_checkout(session, fixture["cart_id"], fixture["mandate_id"])
        await session.commit()

    assert result.proposal.status == ProposalStatus.PROPOSAL_ESCALATED
    assert result.proposal.reason_code == reason_codes.PROPOSAL_LOW_CONFIDENCE
    assert result.cart.subtotal_minor == fixture["original_subtotal"]


async def test_gemini_unavailable_for_merchant_agent_still_completes_checkout() -> None:
    """If Gemini is unreachable for the merchant agent, checkout still completes with the original cart (fail soft)."""
    fixture = await _build_fixture()
    factory = get_session_factory()
    async with factory() as session:
        with patch(MERCHANT_PATCH_TARGET, new=AsyncMock(side_effect=GeminiUnavailableError("no key"))):
            result = await request_checkout(session, fixture["cart_id"], fixture["mandate_id"])
        await session.commit()

    assert result.proposal.status in (ProposalStatus.NO_PROPOSAL, ProposalStatus.ORIGINAL_CART_RETAINED)
    assert result.cart.subtotal_minor == fixture["original_subtotal"]
