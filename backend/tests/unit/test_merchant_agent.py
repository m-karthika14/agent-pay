"""
Purpose: Unit tests for the Merchant Revenue Agent (plan.md Section 13),
exercising run_merchant_agent() end-to-end against a real database but with
LLM calls mocked -- no live GROQ_API_KEY is required to run this suite,
mirroring how Razorpay's create_order() is mocked in the Phase 4/5 test
suites (tests/integration/test_webhooks.py, tests/integration/test_mcp_tools.py).

Each test builds its own isolated merchant/user/products/mandate/cart with
unique identifiers (same pattern as tests/integration/test_cart_checkout.py).
This matters here in particular because app.catalog.service.list_products()
lists the FULL active catalog with no merchant scoping (plan.md Section 18:
UrbanNest is a single demo merchant), so other tests' leftover products may
appear in candidate_products/inventory_results alongside this test's own --
every assertion here is keyed off this test's own product ids, never off
"the only candidate present."

classify_with_schema() is patched where app.agents.merchant.nodes imported
it (not at its definition in app.ai.llm_client), per the standard
unittest.mock rule of patching the name as looked up by the caller.
"""
import os
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from app.agents.merchant.nodes import _CandidateProposal, _CandidateProposalList
from app.agents.merchant.prompts import build_merchant_agent_system_prompt
from app.agents.merchant.runner import run_merchant_agent
from app.ai.errors import LLMUnavailableError
from app.carts.service import add_cart_item, create_cart
from app.db.models.inventory import Inventory
from app.db.models.merchant import Merchant
from app.db.models.product import Product
from app.db.models.user import User
from app.db.session import get_session_factory
from app.mandates.service import create_mandate
from app.policy import reason_codes
from app.schemas.mandate import MandateIntent, MandatePayload
from app.schemas.proposal import ProposalStatus
from app.services.checkout_service import request_checkout

PATCH_TARGET = "app.agents.merchant.nodes.classify_with_schema"
REAL_LLM_ENV_VAR = "REAL_LLM_TESTS"


async def _build_fixture() -> dict:
    """
    Create an isolated merchant, user, mandate, and a frozen cart containing
    one electronics product, plus extra candidate products for the agent to
    consider:
      - `allowed`: electronics, in stock -- a valid upsell candidate.
      - `out_of_stock`: electronics, zero stock -- must never be proposed.
      - `forbidden`/`forbidden2`/`forbidden3`: "accessories" category, not in
        the mandate's allowed_categories -- must always be rejected by
        submit_proposal. Three distinct products so a test can exhaust the
        full MAX_MERCHANT_PROPOSALS revision loop (each retry excludes
        already-tried product ids, so reusing one id would stop the loop early).

    Returns a dict of product ids and the frozen cart_id/mandate_id, for
    tests to reference without holding onto detached ORM instances.
    """
    factory = get_session_factory()
    unique = uuid.uuid4().hex[:8]
    async with factory() as session:
        merchant = Merchant(slug=f"agent-test-{unique}", name="Agent Test Merchant", currency="INR")
        user = User(email=f"agent-test-{unique}@agentpay.test", name="Agent Test User")
        session.add_all([merchant, user])
        await session.flush()

        cart_product = Product(
            merchant_id=merchant.id, sku=f"CART-{unique}", name="Cart Item", description="d",
            price_minor=100_000, currency="INR", category="electronics", is_active=True,
        )
        allowed = Product(
            merchant_id=merchant.id, sku=f"ALLOWED-{unique}", name="Allowed Upsell", description="d",
            price_minor=50_000, currency="INR", category="electronics", is_active=True,
        )
        out_of_stock = Product(
            merchant_id=merchant.id, sku=f"OOS-{unique}", name="Out Of Stock Upsell", description="d",
            price_minor=30_000, currency="INR", category="electronics", is_active=True,
        )
        forbidden = Product(
            merchant_id=merchant.id, sku=f"FORBIDDEN-{unique}", name="Forbidden Upsell", description="d",
            price_minor=20_000, currency="INR", category="accessories", is_active=True,
        )
        forbidden2 = Product(
            merchant_id=merchant.id, sku=f"FORBIDDEN2-{unique}", name="Forbidden Upsell 2", description="d",
            price_minor=15_000, currency="INR", category="accessories", is_active=True,
        )
        forbidden3 = Product(
            merchant_id=merchant.id, sku=f"FORBIDDEN3-{unique}", name="Forbidden Upsell 3", description="d",
            price_minor=10_000, currency="INR", category="accessories", is_active=True,
        )
        session.add_all([cart_product, allowed, out_of_stock, forbidden, forbidden2, forbidden3])
        await session.flush()
        session.add_all(
            [
                Inventory(product_id=cart_product.id, quantity=10),
                Inventory(product_id=allowed.id, quantity=10),
                Inventory(product_id=out_of_stock.id, quantity=0),
                Inventory(product_id=forbidden.id, quantity=10),
                Inventory(product_id=forbidden2.id, quantity=10),
                Inventory(product_id=forbidden3.id, quantity=10),
            ]
        )
        await session.commit()

        payload = MandatePayload(
            mandate_id=f"M-agent-test-{unique}",
            merchant_id=str(merchant.id),
            currency="INR",
            max_amount=500_000,
            allowed_categories=["electronics"],
            allow_addons=False,
            delivery_requirement="under_3_days",
            single_use=True,
            expires_at=datetime.now(UTC) + timedelta(days=1),
            intent=MandateIntent(product_type="test widget"),
        )
        await create_mandate(session, payload, user.id, merchant.id)
        await session.commit()

        cart = await create_cart(session, user.id, merchant.id, "INR")
        await add_cart_item(session, uuid.UUID(cart.cart_id), cart_product.id, 1)
        await session.commit()

        await request_checkout(session, uuid.UUID(cart.cart_id), payload.mandate_id)
        await session.commit()

        return {
            "cart_id": uuid.UUID(cart.cart_id),
            "mandate_id": payload.mandate_id,
            "allowed_id": str(allowed.id),
            "out_of_stock_id": str(out_of_stock.id),
            "forbidden_id": str(forbidden.id),
            "forbidden2_id": str(forbidden2.id),
            "forbidden3_id": str(forbidden3.id),
        }


def _candidate_list(*entries: tuple[str, int]) -> _CandidateProposalList:
    """Build a _CandidateProposalList as if the LLM had returned it, from (product_id, value_add) pairs."""
    return _CandidateProposalList(
        candidates=[
            _CandidateProposal(product_id=pid, quantity=1, reason="test reason", estimated_value_add_minor=value)
            for pid, value in entries
        ]
    )


async def test_llm_unavailable_falls_back_to_no_proposal() -> None:
    """If the LLM can't be reached, the agent must fail soft to NO_PROPOSAL, never crash or block."""
    fixture = await _build_fixture()
    factory = get_session_factory()
    async with factory() as session:
        with patch(PATCH_TARGET, new=AsyncMock(side_effect=LLMUnavailableError("no key"))):
            result = await run_merchant_agent(
                session, fixture["cart_id"], fixture["mandate_id"], 500_000, ["electronics"]
            )
        await session.commit()

    assert result["final_status"] == ProposalStatus.NO_PROPOSAL
    assert result["final_proposal"] is None
    assert result["attempt_count"] == 0


async def test_allowed_candidate_is_accepted_on_first_try() -> None:
    """A candidate that passes amount/category/inventory checks is accepted immediately."""
    fixture = await _build_fixture()
    candidates = _candidate_list((fixture["allowed_id"], 50_000))
    factory = get_session_factory()
    async with factory() as session:
        with patch(PATCH_TARGET, new=AsyncMock(return_value=candidates)):
            result = await run_merchant_agent(
                session, fixture["cart_id"], fixture["mandate_id"], 500_000, ["electronics"]
            )
        await session.commit()

    assert result["final_status"] == ProposalStatus.PROPOSAL_ALLOWED
    assert result["final_proposal"]["product_id"] == fixture["allowed_id"]
    assert result["attempt_count"] == 1
    assert result["proposal_history"][0]["allowed"] is True


async def test_forbidden_category_candidate_is_rejected_and_original_cart_retained() -> None:
    """A single out-of-policy candidate is rejected, and with no other candidates to try, the original cart is retained."""
    fixture = await _build_fixture()
    candidates = _candidate_list((fixture["forbidden_id"], 20_000))
    factory = get_session_factory()
    async with factory() as session:
        with patch(PATCH_TARGET, new=AsyncMock(return_value=candidates)):
            result = await run_merchant_agent(
                session, fixture["cart_id"], fixture["mandate_id"], 500_000, ["electronics"]
            )
        await session.commit()

    assert result["final_status"] == ProposalStatus.ORIGINAL_CART_RETAINED
    assert result["final_proposal"] is None
    assert result["attempt_count"] == 1
    assert result["proposal_history"][0]["allowed"] is False
    assert result["proposal_history"][0]["reason_code"] == reason_codes.MANDATE_CATEGORY_FORBIDDEN


async def test_out_of_stock_candidate_is_rejected_via_inventory_check() -> None:
    """A candidate proposing more quantity than available is rejected with INVENTORY_INVALID."""
    fixture = await _build_fixture()
    candidates = _candidate_list((fixture["out_of_stock_id"], 30_000))
    factory = get_session_factory()
    async with factory() as session:
        with patch(PATCH_TARGET, new=AsyncMock(return_value=candidates)):
            result = await run_merchant_agent(
                session, fixture["cart_id"], fixture["mandate_id"], 500_000, ["electronics"]
            )
        await session.commit()

    assert result["final_status"] == ProposalStatus.ORIGINAL_CART_RETAINED
    assert result["proposal_history"][0]["reason_code"] == reason_codes.INVENTORY_INVALID


async def test_revision_loop_tries_next_best_candidate_after_a_rejection() -> None:
    """When the top-ranked candidate is rejected, the agent revises to the next-best untried candidate."""
    fixture = await _build_fixture()
    candidates = _candidate_list(
        (fixture["forbidden_id"], 90_000),  # ranked first (highest value) but will be rejected
        (fixture["allowed_id"], 50_000),  # tried second, and accepted
    )
    factory = get_session_factory()
    async with factory() as session:
        with patch(PATCH_TARGET, new=AsyncMock(return_value=candidates)):
            result = await run_merchant_agent(
                session, fixture["cart_id"], fixture["mandate_id"], 500_000, ["electronics"]
            )
        await session.commit()

    assert result["final_status"] == ProposalStatus.PROPOSAL_ALLOWED
    assert result["final_proposal"]["product_id"] == fixture["allowed_id"]
    assert result["attempt_count"] == 2
    assert result["proposal_history"][0]["allowed"] is False
    assert result["proposal_history"][1]["allowed"] is True


async def test_all_candidates_rejected_retains_original_cart_after_max_attempts() -> None:
    """If every ranked candidate is rejected, the agent stops at MAX_MERCHANT_PROPOSALS and retains the original cart."""
    fixture = await _build_fixture()
    candidates = _candidate_list(
        (fixture["forbidden_id"], 90_000),
        (fixture["forbidden2_id"], 80_000),
        (fixture["forbidden3_id"], 70_000),
    )
    factory = get_session_factory()
    async with factory() as session:
        with patch(PATCH_TARGET, new=AsyncMock(return_value=candidates)):
            result = await run_merchant_agent(
                session, fixture["cart_id"], fixture["mandate_id"], 500_000, ["electronics"]
            )
        await session.commit()

    assert result["final_status"] == ProposalStatus.ORIGINAL_CART_RETAINED
    assert result["final_proposal"] is None
    assert result["attempt_count"] == 3
    assert all(entry["allowed"] is False for entry in result["proposal_history"])
    assert {entry["proposal"]["product_id"] for entry in result["proposal_history"]} == {
        fixture["forbidden_id"],
        fixture["forbidden2_id"],
        fixture["forbidden3_id"],
    }


async def test_out_of_category_and_over_headroom_candidates_are_never_shown_to_the_llm() -> None:
    """
    Reported live bug: the agent previously ranked every in-stock product
    purely by "value add," with no visibility into the mandate's real
    category/budget constraints -- it could burn all its attempts on
    candidates that were always going to be rejected downstream, even when
    a real, in-budget, in-category candidate never got a look because the
    LLM's own ranking (blind to constraints) never surfaced it.

    This test proves the deterministic fix directly: when NOTHING in the
    catalog could ever be accepted (wrong category, or priced above the
    mandate's remaining headroom), search_relevant_products's filter empties
    candidate_products before generate_candidates runs -- so the LLM is
    never even called, and the outcome is NO_PROPOSAL with zero attempts,
    not three wasted ones.
    """
    factory = get_session_factory()
    unique = uuid.uuid4().hex[:8]
    async with factory() as session:
        merchant = Merchant(slug=f"agent-filter-test-{unique}", name="Agent Filter Test Merchant", currency="INR")
        user = User(email=f"agent-filter-test-{unique}@agentpay.test", name="Agent Filter Test User")
        session.add_all([merchant, user])
        await session.flush()

        cart_product = Product(
            merchant_id=merchant.id, sku=f"CART-{unique}", name="Cart Item", description="d",
            price_minor=100_000, currency="INR", category="electronics", is_active=True,
        )
        wrong_category = Product(
            merchant_id=merchant.id, sku=f"WRONGCAT-{unique}", name="Wrong Category Upsell", description="d",
            price_minor=5_000, currency="INR", category="accessories", is_active=True,  # not in allowed_categories
        )
        too_expensive = Product(
            merchant_id=merchant.id, sku=f"EXPENSIVE-{unique}", name="Too Expensive Upsell", description="d",
            price_minor=50_000, currency="INR", category="electronics", is_active=True,  # right category, over headroom
        )
        session.add_all([cart_product, wrong_category, too_expensive])
        await session.flush()
        session.add_all(
            [
                Inventory(product_id=cart_product.id, quantity=10),
                Inventory(product_id=wrong_category.id, quantity=10),
                Inventory(product_id=too_expensive.id, quantity=10),
            ]
        )
        await session.commit()

        payload = MandatePayload(
            mandate_id=f"M-agent-filter-test-{unique}",
            merchant_id=str(merchant.id),
            currency="INR",
            max_amount=110_000,  # Rs 10,000 headroom above the cart's Rs 100,000 -- too_expensive (Rs 50,000) can't fit
            allowed_categories=["electronics"],
            allow_addons=False,
            delivery_requirement="under_3_days",
            single_use=True,
            expires_at=datetime.now(UTC) + timedelta(days=1),
            intent=MandateIntent(product_type="test widget"),
        )
        await create_mandate(session, payload, user.id, merchant.id)
        await session.commit()

        cart = await create_cart(session, user.id, merchant.id, "INR")
        await add_cart_item(session, uuid.UUID(cart.cart_id), cart_product.id, 1)
        await session.commit()

        await request_checkout(session, uuid.UUID(cart.cart_id), payload.mandate_id)
        await session.commit()

        llm_mock = AsyncMock(return_value=_candidate_list())
        with patch(PATCH_TARGET, new=llm_mock):
            result = await run_merchant_agent(
                session, uuid.UUID(cart.cart_id), payload.mandate_id, payload.max_amount, payload.allowed_categories
            )
        await session.commit()

    llm_mock.assert_not_called()
    assert result["final_status"] == ProposalStatus.NO_PROPOSAL
    assert result["final_proposal"] is None
    assert result["attempt_count"] == 0


def test_system_prompt_states_the_complementarity_criteria() -> None:
    """
    Regression guard for the strengthened prompt (plan.md Phase 4.4, added
    after a live reported case where the agent proposed a second pair of
    earbuds as an "upsell" for a cart that already had one -- same catalog
    category, no complementary purpose). This doesn't prove the LLM obeys
    the instruction (see the REAL_LLM_TESTS-gated test below for that) --
    it just prevents someone from silently reverting the guidance itself,
    since plan.md Section 13.2 requires this prompt to stay a committed,
    inspectable artifact.
    """
    prompt = build_merchant_agent_system_prompt("Test Merchant")
    assert "complementary" in prompt.lower()
    assert "duplicat" in prompt.lower()  # matches "duplicate"/"duplicating"
    assert "category" in prompt.lower() and "not evidence of relevance" in prompt.lower()


@pytest.mark.skipif(
    os.environ.get(REAL_LLM_ENV_VAR, "").lower() not in {"1", "true", "yes"},
    reason=f"Live LLM reasoning check against real Groq -- set {REAL_LLM_ENV_VAR}=1 to run.",
)
async def test_real_llm_does_not_propose_a_duplicate_primary_product() -> None:
    """
    Live reported bug, run against the REAL Groq model (not mocked): the
    Merchant Agent proposed a second pair of earbuds as an "upsell" for a
    cart that already had one -- basket value went up, but it wasn't a
    sensible complementary purchase. The candidate set here deliberately
    includes both the duplicate (another pair of earbuds, higher price) and
    a genuine complement (a case, lower price) so a value-blind ranking
    would favor the duplicate -- this test is the actual proof the
    strengthened prompt (plan.md Phase 4.4) steers the model away from it.

    Skipped by default (see REAL_LLM_ENV_VAR) since it needs a real
    GROQ_API_KEY and hits the live API -- run explicitly before a demo.
    """
    factory = get_session_factory()
    unique = uuid.uuid4().hex[:8]
    async with factory() as session:
        merchant = Merchant(slug=f"agent-dup-test-{unique}", name="Agent Duplicate Test Merchant", currency="INR")
        user = User(email=f"agent-dup-test-{unique}@agentpay.test", name="Agent Duplicate Test User")
        session.add_all([merchant, user])
        await session.flush()

        earbuds_in_cart = Product(
            merchant_id=merchant.id, sku=f"EARBUDS-{unique}", name="Wireless Earbuds Alpha", description="d",
            price_minor=799_900, currency="INR", category="audio", is_active=True,
        )
        duplicate_earbuds = Product(
            merchant_id=merchant.id, sku=f"EARBUDS2-{unique}", name="Wireless Earbuds Beta", description="d",
            price_minor=179_900, currency="INR", category="audio", is_active=True,
        )
        case = Product(
            merchant_id=merchant.id, sku=f"CASE-{unique}", name="Protective Earbuds Case", description="d",
            price_minor=29_900, currency="INR", category="accessories", is_active=True,
        )
        session.add_all([earbuds_in_cart, duplicate_earbuds, case])
        await session.flush()
        session.add_all(
            [
                Inventory(product_id=earbuds_in_cart.id, quantity=10),
                Inventory(product_id=duplicate_earbuds.id, quantity=10),
                Inventory(product_id=case.id, quantity=10),
            ]
        )
        await session.commit()

        payload = MandatePayload(
            mandate_id=f"M-agent-dup-test-{unique}",
            merchant_id=str(merchant.id),
            currency="INR",
            max_amount=999_900,  # headroom comfortably covers both candidates
            allowed_categories=["audio", "accessories"],
            allow_addons=True,
            delivery_requirement="under_3_days",
            single_use=True,
            expires_at=datetime.now(UTC) + timedelta(days=1),
            intent=MandateIntent(product_type="wireless earbuds"),
        )
        await create_mandate(session, payload, user.id, merchant.id)
        await session.commit()

        cart = await create_cart(session, user.id, merchant.id, "INR")
        await add_cart_item(session, uuid.UUID(cart.cart_id), earbuds_in_cart.id, 1)
        await session.commit()

        await request_checkout(session, uuid.UUID(cart.cart_id), payload.mandate_id)
        await session.commit()

        result = await run_merchant_agent(
            session, uuid.UUID(cart.cart_id), payload.mandate_id, payload.max_amount, payload.allowed_categories
        )
        await session.commit()

    proposed_ids = {entry["proposal"]["product_id"] for entry in result["proposal_history"]}
    assert str(duplicate_earbuds.id) not in proposed_ids, (
        "The Merchant Agent proposed a second pair of earbuds as an upsell for a cart that already had one -- "
        f"proposal_history was {result['proposal_history']}"
    )
