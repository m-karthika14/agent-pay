# AgentPay — FINAL PHASE PLAN

This is the **final execution plan** based on the frozen AgentPay specification and 7-day calendar. The core product, actors, hard-boundary rules, evaluation rules, stack, and freeze point are all fixed. 

## PHASE 0 — SCOPE FREEZE

### Sunday, 23 Aug — before coding

### Product

**AgentPay:** merchant-side authorization gateway that makes a Razorpay merchant transactable by external AI buyers while protecting the user's signed spending and intent from revenue-maximizing merchant agents. 

### Actors

| Actor                      | Role                                          |
| -------------------------- | --------------------------------------------- |
| **User**                   | Gives purchase authorization                  |
| **Claude**                 | External AI buyer; not built by you           |
| **Merchant Revenue Agent** | Your **one** AI agent; maximizes basket value |
| **AgentPay**               | Gateway / deterministic money boundary        |
| **Razorpay**               | Test-mode payment execution                   |

### Rules that never change

**1. LLM can only subtract permission.** Hard checks run first.

**2. Fail closed.** Unavailable/ambiguous/low-confidence intent → block + escalation.

**3. User intent is signed into the mandate.**

**4. Cart is frozen and hashed separately.** `cart_hash` is not part of the mandate. 

### Merchant agent

It may:

* propose
* revise
* make at most **3 proposals**
* read block reasons

It may never:

* execute payment
* modify mandate
* call Razorpay
* bypass AgentPay

After 3 failed proposals, the original cart continues. 

### Evaluation rules

Freeze these before evaluation:

* Cap-only vs Intent-aware
* same persona prompts in both arms
* persona prompts frozen before either arm
* intent threshold frozen before evaluation
* ceiling drift uses completed transactions only
* abandonment reported separately
* adversarial suite is supporting evidence, not your main causal claim 

---

# PHASE 1 — SECURITY FOUNDATION

## Sunday, 23 Aug

### Goal

Build the trust boundary.

### Build

**1. Failing security test first**

```text
valid mandate
→ sign
→ modify one byte
→ verify
→ REJECT
```

**2. Mandate schema**

```text
mandate_id
merchant_id
currency
max_amount
allowed_categories
allow_addons
delivery_requirement
single_use
expires_at
intent
```

**3. Canonicalization**

Deterministic serialization before signing.

**4. Ed25519**

```text
sign_mandate()
verify_mandate()
```

**5. Deterministic verification**

Signature, merchant, currency, amount, category, expiry, single-use, mandate status, replay. 

**6. PostgreSQL**

```text
users
merchants
mandates
products
inventory
carts
cart_items
orders
transactions
audit_events
```

**7. Hash-chain audit**

```text
event_id
mandate_id
event_type
timestamp
payload_hash
previous_hash
event_hash
decision
reason_code
```

### End-of-day test

```text
Valid mandate     → PASS
Tampered mandate  → REJECT
Expired mandate   → REJECT
Replay            → REJECT
Audit             → STORED
Hash chain        → VALID
```

Do **not** build Claude, MCP, Razorpay, LangGraph, or frontend polish yet. 

---

# PHASE 2 — CORE MERCHANT BACKEND

## Monday, 24 Aug — Morning

### Goal

Get the merchant/backend working before adding MCP.

### Build

**FastAPI**

```text
app/
├── api/
├── mandates/
├── carts/
├── policies/
├── payments/
├── audit/
├── agents/
├── db/
└── main.py
```

### Catalog APIs

```text
GET /products
GET /products/:id
GET /inventory/:id
```

Machine-readable:

```text
product_id
name
price
currency
category
availability
delivery
return_policy
```

### UrbanNest

Keep it tiny:

```text
Wireless Earbuds   ₹2,499
Smart Watch         ₹3,499
Power Bank          ₹1,299
Protective Case       ₹299
Premium Bundle      ₹2,799
```

### Cart lifecycle

```text
create_cart
add_to_cart
update_cart
get_cart
```

At this stage the cart is mutable. 

---

# PHASE 3 — CART INTEGRITY + POLICY

## Monday, 24 Aug — Afternoon

### Goal

Build the actual deterministic AgentPay boundary.

### `request_checkout`

```text
Fetch cart
→ validate inventory
→ validate prices
→ validate mandate
→ canonicalize cart
→ SHA-256
→ freeze cart
→ store cart_hash
```

The mandate and frozen cart hash remain **separate artifacts**. 

### Deterministic policy engine

Check:

```text
signature
mandate active
merchant
category
amount
currency
cart integrity
inventory
mandate unused
replay
idempotency
```

### Idempotency

```text
request 1 → execute
same request again → existing result / reject
```

### Cart manipulation

```text
frozen hash != final hash
→ BLOCK
```

### Acceptance

Authorized cart freezes, modified cart fails, unauthorized amount fails, replay fails, duplicate request fails. 

---

# PHASE 4 — RAZORPAY + DEPLOYMENT

## Monday, 24 Aug — Evening

### Goal

Get a real payment path working before MCP.

### Razorpay Test Mode

```text
Create order
→ test payment flow
→ payment result
```

### Webhooks

Handle:

* success
* failure
* duplicate delivery
* unexpected state

Validate webhook signatures.

### Reconciliation

```text
AgentPay transaction
↔ Razorpay order
↔ Razorpay payment
↔ final order state
```

### Audit events

```text
ORDER_CREATED
PAYMENT_REQUESTED
PAYMENT_CAPTURED
PAYMENT_FAILED
ORDER_UPDATED
```

### Deploy publicly

```text
React → Vercel
FastAPI → Render/Railway
PostgreSQL → managed DB
```

### Acceptance

```text
AgentPay
→ Razorpay Test Mode
→ payment
→ webhook
→ PostgreSQL
→ audit
```

This public deployment happens **before MCP**, so MCP is wrapping already-working APIs. 

---

# PHASE 5 — MCP + CLAUDE

## Tuesday, 25 Aug

# 🚨 FREEZE POINT

### Goal

Make the merchant AI-transactable.

Expose:

```text
search_products()
get_product()
create_cart()
add_to_cart()
request_checkout()
complete_purchase()
```

Connect **Claude as the external buyer**.

Flow:

```text
search
→ inspect
→ create cart
→ add item
→ request checkout
→ complete purchase
```

Then:

```text
Claude
→ MCP
→ AgentPay
→ Razorpay Test Mode
→ Webhook
→ Order
```

### THIS IS THE CORE SUBMISSION

Once this works, the core system exists. Record a basic working video immediately. 

---

# PHASE 6 — MERCHANT REVENUE AGENT

## Wednesday, 26 Aug

### Goal

Create the revenue pressure that AgentPay must govern.

### Your ONE agent

**LangGraph + LLM**

Workflow:

```text
Analyze cart
→ search products
→ check inventory
→ generate upsells/bundles
→ rank revenue opportunity
→ submit ONE proposal
```

Tools:

```text
get_cart()
search_products()
get_product()
check_inventory()
calculate_bundle()
submit_proposal()
```

### Hard boundary

The agent can:

✅ propose

It cannot:

❌ modify mandate
❌ execute payment
❌ call Razorpay
❌ directly authorize purchase

### Revision loop

```text
Proposal 1
→ BLOCK + reason
→ revise

Proposal 2
→ BLOCK + reason
→ revise

Proposal 3
```

After three failures:

**original cart retained.**

### No-proposal path

```text
original cart
→ re-validation
→ payment
```

The merchant agent is **advisory**, not mandatory. 

### Keep its prompt in the repo

Show the merchant-agent system prompt on your technical slide. Its objective should genuinely be to maximize basket value. 

---

# PHASE 7 — INTENT GATE

## Thursday, 27 Aug — Morning

### Goal

Handle semantic intent separately from deterministic policy.

### Inputs

```text
Original buyer request
Signed intent
Original cart
Proposed modification
```

Example:

```text
User:
"Buy earbuds under ₹3,000. No accessories."

Merchant:
"Earbuds + case = ₹2,798"

Intent gate:
BLOCK
Reason: accessory conflicts with signed intent
```

### Important

The intent gate is **not an agent**.

It is a single LLM classification step.

### Fail closed

If:

```text
LLM unavailable
low confidence
ambiguous
```

then:

```text
BLOCK
→ human escalation
```

### Freeze confidence threshold

Use a small hand-labeled calibration set, choose the threshold, document it, and **do not change it during evaluation**. 

---

# PHASE 8 — FINAL RE-VALIDATION + ESCALATION

## Thursday, 27 Aug — Afternoon

After intent approval:

```text
Intent Gate
→ deterministic re-validation
→ Razorpay
```

Re-check:

```text
amount
merchant
category
currency
cart hash
inventory
mandate
single-use
replay
idempotency
```

If intent is ambiguous:

```text
BLOCK
→ ESCALATE
→ human decision
```

Never:

```text
unknown → allow
```

This is what ensures the LLM cannot silently expand the money boundary. 

---

# PHASE 9 — EVALUATION HARNESS

## Friday, 28 Aug — Morning

### Freeze the personas FIRST

Use:

```text
Price-sensitive
Convenience-first
Literal-minded
Prompt-injected
```

Freeze prompts before either arm runs.

### Arm A — Cap-only

```text
Hard spending constraints
```

### Arm B — Intent-aware

```text
Hard constraints
+
signed intent
+
intent gate
```

Keep identical:

* merchant agent
* products
* starting carts
* personas
* prompts 

---

# PHASE 10 — METRICS

## Friday, 28 Aug

## Primary metric — Mandate Ceiling Drift

[
\text{Ceiling Drift}
====================

\frac{\text{Final Completed Spend}}
{\text{Authorized Spending Cap}}
]

### Denominator rule

Only **completed transactions**.

Do **not** count an abandonment as ₹0.

Report abandonment separately.

### Supporting metrics

```text
Legitimate completion rate
Abandonment rate
Correct escalation rate
Violations caught / attempted
Replay protection
Price-change protection
Prompt-injection protection
Duplicate protection
```

### Adversarial suite

Approximately 30 cases:

```text
Overspend
Cap splitting
Expired mandate
Replay
Wrong merchant
Wrong category
Price change
Cart modification
Duplicate submit
Prompt injection
Currency mismatch
Unit confusion
Out of stock
Merchant upsell
Duplicate payment
```

Treat this as supporting evidence because you wrote the scenarios.

### Sensitivity

Run:

```text
-30%
baseline
+30%
```

Do not modify the evaluation setup after seeing results. 

---

# PHASE 11 — MERCHANT CONSOLE

## Friday, 28 Aug — Afternoon

### Goal

Make the technical system easy for judges to understand.

Show:

### Transaction

```text
Buyer
Intent
Mandate
Cart
Merchant proposal
Intent decision
Policy decision
Razorpay state
```

### Decision trace

```text
Hard checks → PASS
Merchant proposal → ₹X
Intent gate → BLOCK
Reason → ...
Original cart → retained
Payment → completed
```

### Audit viewer

```text
event
timestamp
decision
reason
previous_hash
current_hash
```

Keep the frontend thin. 

---

# PHASE 12 — FAILURE DEMOS

## Friday, 28 Aug — Evening

Prepare:

### A. Overspend

```text
Authorized ₹3,000
Requested ₹5,999
→ BLOCK
→ LLM never invoked
```

### B. Merchant upsell violation

```text
Cap passes
Intent fails
→ BLOCK
```

### C. Mandate replay

```text
single-use already consumed
→ BLOCK
```

### D. Cart manipulation

```text
frozen hash != final hash
→ BLOCK
```

### E. Ambiguous intent

```text
low confidence
→ BLOCK + human escalation
```

Pick the strongest one for the live demo. 

---

# PHASE 13 — DEMO RECORDING

## Friday, 28 Aug

Record the complete flow:

```text
Claude
→ MCP
→ AgentPay
→ Merchant Revenue Agent
→ Intent Gate
→ Razorpay Test Mode
→ Webhook
→ Audit
```

Make a backup recording.

Do not depend on conference Wi-Fi, MCP connectivity, browser state, or API latency. 

---

# PHASE 14 — FINAL PRESENTATION

## Saturday, 29 Aug

### Slide 1 — Problem

```text
Buyer wants user intent
        vs
Merchant wants revenue
```

### Slide 2 — AgentPay

Show architecture.

### Slide 3 — Technical boundary

```text
Hard checks
→ Merchant proposal
→ Intent gate
→ Re-validation
→ Razorpay
```

### Slide 4 — Live agentic commerce

Claude buys through MCP.

### Slide 5 — Attack

Merchant agent pushes the cart.

AgentPay blocks it.

### Slide 6 — Security

Signed mandate + cart hash + audit chain.

### Slide 7 — Evaluation

Show the **real**:

```text
Cap-only ceiling drift
vs
Intent-aware ceiling drift
```

Plus abandonment and escalation.

### Slide 8 — Limitations

State clearly:

> AP2-style mandate concepts used.
> ACP-shaped checkout interface used.
> UAP is not claimed as implemented because there is no public specification we can claim conformance to.
> Evaluation covers the tested attack classes.

### Slide 9 — Closing

> **“Claude buys. The merchant agent sells. AgentPay governs. Razorpay executes.”** 

---

# FINAL 7-DAY CALENDAR

| Date           | Main objective              | Must ship                                                                  |
| -------------- | --------------------------- | -------------------------------------------------------------------------- |
| **Sun 23 Aug** | Security foundation         | Mandate + Ed25519 + verifier + PostgreSQL + audit                          |
| **Mon 24 Aug** | Backend + payments          | FastAPI + catalog + carts + freeze/hash + Razorpay + webhooks + deployment |
| **Tue 25 Aug** | 🔥 **FREEZE POINT**         | MCP + Claude → AgentPay → Razorpay                                         |
| **Wed 26 Aug** | Merchant pressure           | One LangGraph merchant agent + 3-proposal loop                             |
| **Thu 27 Aug** | Safe semantic authorization | Intent gate + frozen threshold + re-validation + escalation                |
| **Fri 28 Aug** | Proof + demo                | Evaluation + metrics + console + failure demos + recording                 |
| **Sat 29 Aug** | Finalization                | Presentation + rehearsal + buffer                                          |



---

# PRIORITY SYSTEM

## 🔴 Tier 1 — MUST WORK

```text
Signed mandates
Deterministic hard checks
Cart freeze/hash
Idempotency
Razorpay Test Mode
Webhooks
Public backend
MCP
Claude end-to-end
Audit trail
```

## 🟠 Tier 2 — Differentiator

```text
Merchant Revenue Agent
Intent Gate
Revision loop
Human escalation
```

## 🟢 Tier 3 — Evidence

```text
Cap-only vs Intent-aware
Ceiling drift
Abandonment
Escalation
Adversarial suite
Sensitivity sweep
```

## 🔵 Tier 4 — Polish

```text
Dashboard
Animations
Fancy UI
Extra visualizations
```

**If time gets tight: cut Tier 4 first. Never sacrifice Tier 1.** 

---

# FINAL ARCHITECTURE

```text
                 CLAUDE
            External AI Buyer
                    │
                   MCP
                    │
                    ▼
          ┌──────────────────┐
          │  HARD CHECKS     │
          │  Deterministic   │
          └────────┬─────────┘
                   │
                   │ PASS
                   │
          ┌────────┴─────────┐
          │                  │
          │  MERCHANT        │
          │  REVENUE AGENT   │
          │  LangGraph       │
          │  ADVISORY ONLY   │
          │  Propose/Revise  │
          │                  │
          └────────┬─────────┘
                   │
                   ▼
             INTENT GATE
                 LLM
                   │
              ALLOW/BLOCK
                   │
                   ▼
          DETERMINISTIC
           RE-VALIDATION
                   │
                   ▼
              RAZORPAY
              TEST MODE
                   │
                WEBHOOK
                   │
             ┌─────┴─────┐
             ▼           ▼
        PostgreSQL   Hash-chain Audit
```

The **merchant agent is the only agent you build**; Claude is the external buyer, and the intent gate is an LLM classifier rather than another agent. 

## The one sentence

> **AgentPay lets external AI buyers transact with a merchant while a revenue-maximizing merchant agent tries to push the cart upward, and the gateway enforces the user's signed spending and intent before any payment executes.** 



--------------------------------
AgentPay — Final Master Build Plan

0. Document Status

Status: FINAL / FROZEN

Project: AgentPay

Track: Razorpay Track 1 — AI Growth & Agentic Commerce

Build window: 23 August 2026 → 29 August 2026

Purpose of this file: This is the single source of truth for the build. Do not introduce new major features, frameworks, agents, protocols, or architecture unless an actual implementation blocker forces a change.

1. Final Product Definition

1.1 One-line product

AgentPay is a merchant-side authorization gateway that makes a Razorpay merchant transactable by external AI buyers while protecting the user's signed spending and intent from revenue-maximizing merchant agents.

1.2 The core thesis

Agentic commerce creates a conflict of incentives:

The user wants the purchase to remain within what they actually authorized.

The external buyer agent wants to complete the user's request.

The merchant revenue agent wants to increase the merchant's basket value.

AgentPay sits at the merchant and enforces the authorization boundary before money moves.

The merchant revenue agent is deliberately optimized to push bundles and upsells. It is therefore a realistic pressure test of the gateway.

Core thesis for the pitch

Agentic upsell is pressure on the mandate layer. AgentPay provides the authorization boundary and measures how much merchant pressure can capture with and without intent enforcement.

1.3 What AgentPay is NOT

AgentPay is not:

an AI shopping chatbot

a marketplace

an Amazon/Flipkart clone

a fraud detector

a generic recommendation engine

an AI that directly holds payment credentials

a system where an LLM has final authority over money

2. Why the Project Fits Track 1

Razorpay Track 1 asks builders to either:

Grow merchant revenue, or

Make a merchant transactable by an AI buyer end-to-end.

AgentPay addresses both in one coherent system.

Revenue growth

The Merchant Revenue Agent proposes:

upsells

cross-sells

bundles

Its objective is to maximize basket value.

AI-transactable merchant

Claude, acting as an external AI buyer, can:

Discover → Select → Cart → Checkout → Payment

through the merchant's machine-readable MCP interface.

Track 1 safety bar

Every money action is:

explainable

bounded

gated

audited

The system also demonstrates a graceful failure.

3. Actors and Responsibilities

3.1 User

The user provides the authorization and intent.

Example:

"Buy good wireless earbuds under ₹3,000. No unnecessary accessories. Delivery within 3 days."

The relevant constraints and intent are encoded into the signed mandate.

3.2 External Buyer Agent — Claude

You do not build this agent.

Claude acts on behalf of the user.

Claude can interact with the merchant through MCP tools:

search_products()
get_product()
create_cart()
add_to_cart()
request_checkout()
complete_purchase()

Claude's responsibility is to find and request a purchase that satisfies the user's request.

Important payment wording

Claude drives the commerce transaction, but Claude is not the component that owns Razorpay credentials or directly types payment credentials.

Correct phrasing:

Claude drives the purchase through the merchant interface; after AgentPay authorizes the transaction, Razorpay Test Mode executes the payment flow.

3.3 Merchant Revenue Agent — your one agent

This is the only AI agent you build.

Use LangGraph only for this agent because the agent has a real multi-step tool-using workflow.

Objective

Maximize merchant basket value using relevant upsells, cross-sells, and bundles.

Example:

Cart:
Wireless Earbuds — ₹2,499

Merchant Agent proposal:
Add Protective Case — ₹299

It may

inspect the cart

inspect products

check inventory

generate candidate offers

rank revenue opportunities

submit one proposal

revise a proposal after receiving a block reason

It may NOT

modify the signed mandate

authorize payment

directly modify the authorized transaction

call Razorpay

bypass AgentPay

execute a payment

It only proposes.

3.4 AgentPay Gateway

AgentPay is the actual product.

It is the merchant-side referee between the user authorization, external buyer agent, and merchant revenue agent.

AgentPay owns:

mandate verification

hard policy enforcement

cart integrity

idempotency

intent gating

final deterministic re-validation

Razorpay integration

auditability

3.5 Razorpay

Razorpay is the payment layer.

Use Razorpay Test Mode only.

No real money is required for the hackathon demo.

4. Non-Negotiable Security Rules

These rules are frozen and apply to the entire project.

Rule 1 — The model can only subtract permission

LLMs may recommend/block/escalate.

No LLM output can grant authority that the deterministic policy layer did not already permit.

Rule 2 — Hard constraints run first

Before any intent LLM is invoked, deterministic checks must pass.

If a hard check fails:

BLOCK
↓
Reason code
↓
Audit

The intent LLM is not invoked.

Rule 3 — Fail closed

If intent reasoning is:

unavailable

low confidence

ambiguous

then:

BLOCK
↓
ESCALATE TO HUMAN

Never default to allow.

Rule 4 — Intent is signed into the mandate

Intent/constraints are captured at authorization time and cannot be rewritten by the merchant agent.

Rule 5 — Cart hash is separate from the mandate

The mandate contains the buyer's authorization constraints.

The cart is frozen and hashed later, at request_checkout.

Do not put cart_hash inside the mandate.

The system therefore has two artifacts:

SIGNED MANDATE
+
FROZEN CART + CART HASH

Rule 6 — Merchant agent is advisory only

The merchant agent proposes changes.

It cannot execute them.

Rule 7 — Maximum three merchant proposals

For a cart:

Proposal 1 → block/allow
Proposal 2 → block/allow
Proposal 3 → block/allow

If three proposals are blocked, the original cart continues.

No infinite agent loop.

5. Final End-to-End Architecture

                         CLAUDE
                    External AI Buyer
                           │
                          MCP
                           │
                           ▼
                 ┌──────────────────┐
                 │ 1. HARD CHECKS   │
                 │   Deterministic  │
                 └────────┬─────────┘
                          │
                PASS ─────┘
                          │
            ┌─────────────┴─────────────┐
            │                           │
            │   Merchant Revenue Agent  │
            │      (LangGraph)          │
            │      ADVISORY ONLY        │
            │   proposes / revises      │
            │                           │
            └─────────────┬─────────────┘
                          │
                          ▼
                 ┌──────────────────┐
                 │ 2. INTENT GATE  │
                 │    LLM call     │
                 └────────┬─────────┘
                          │
                    ALLOW / BLOCK
                          │
                          ▼
                 ┌──────────────────┐
                 │ 3. FINAL HARD    │
                 │    RE-VALIDATION │
                 └────────┬─────────┘
                          │
                          ▼
                    RAZORPAY TEST
                          │
                       WEBHOOK
                          │
             ┌────────────┴────────────┐
             ▼                         ▼
        PostgreSQL                Audit Hash Chain

Important visual/logic interpretation

The merchant agent is advisory and should not be interpreted as a mandatory authorization stage.

The main authorization path is:

Hard Checks
→ Intent Gate (when a proposal exists)
→ Final Deterministic Re-validation
→ Razorpay

If there is no merchant proposal, the original cart proceeds directly from hard checks to final re-validation.

If the merchant proposal is rejected, it is the proposal that is rejected—not automatically the whole transaction.

6. Outcome Semantics

Use distinct outcomes in code and audit logs.

6.1 TRANSACTION_BLOCKED — terminal

Use when the buyer's actual transaction violates a hard authorization rule.

Examples:

amount exceeds cap

mandate expired

wrong merchant

wrong category

invalid signature

replay

cart integrity failure

duplicate payment

post-modification hard validation failure

The transaction stops.

6.2 PROPOSAL_REJECTED — non-terminal

Use when the merchant revenue agent's proposed upsell/cross-sell is rejected.

The original cart remains available.

Example:

Merchant proposal:
Earbuds + accessory

Intent gate:
PROPOSAL_REJECTED

Result:
Original cart continues

This distinction must exist in the implementation, reason-code taxonomy, audit log, and architecture diagram.

6.3 ESCALATION_REQUIRED

Use when semantic intent is ambiguous or the intent model has insufficient confidence.

The default is still fail-closed.

7. Signed Mandate

7.1 Purpose

The mandate is the user's authorization boundary.

7.2 Suggested fields

{
  "mandate_id": "M-001",
  "merchant_id": "urbannest",
  "currency": "INR",
  "max_amount": 3000,
  "allowed_categories": ["electronics"],
  "allow_addons": false,
  "delivery_requirement": "under_3_days",
  "single_use": true,
  "expires_at": "...",
  "intent": {
    "product_type": "wireless earbuds",
    "notes": "no unnecessary accessories"
  }
}

Do not include cart_hash here.

7.3 Signing

Canonicalize the payload and sign with Ed25519.

Implement:

sign_mandate()
verify_mandate()

7.4 Tamper test

Write this before building anything else:

Create valid mandate
↓
Sign it
↓
Modify one byte
↓
Verify
↓
ASSERT REJECT

This is the first security test in the repository.

8. Cart Integrity

8.1 Authorization artifact vs cart artifact

The mandate says what the user authorizes.

The cart says what is actually being purchased.

They are separate.

8.2 Freeze point

At request_checkout:

Fetch current cart
↓
Validate product price
↓
Validate inventory
↓
Validate mandate
↓
Canonicalize cart
↓
SHA-256
↓
Freeze cart
↓
Store cart_hash

8.3 Final re-validation

After any merchant proposal is accepted by the intent gate:

Recompute/verify final cart state
↓
Compare against authorized frozen state
↓
Run all deterministic constraints again

Any mismatch must fail closed.

9. Deterministic Hard Policy Engine

The hard policy engine is ordinary Python code, not an agent.

Checks include:

signature valid?
mandate active?
merchant allowed?
category allowed?
amount <= cap?
currency correct?
original frozen cart valid?
final cart hash valid?
inventory valid?
mandate unused?
replay absent?
idempotency valid?

Pre-LLM behavior

If any hard check fails:

TRANSACTION_BLOCKED
LLM not invoked
Audit reason code

Post-LLM behavior

After an intent-allowed merchant proposal:

FINAL HARD RE-VALIDATION
→ PASS → Razorpay
→ FAIL → TRANSACTION_BLOCKED

10. Merchant Revenue Agent — LangGraph

10.1 Why LangGraph is used

LangGraph is used only for the Merchant Revenue Agent because the agent has a real multi-step, stateful, tool-using workflow.

Do not use LangGraph for the gateway authorization layer.

10.2 Workflow

START
↓
Analyze current cart
↓
Search relevant products
↓
Check inventory
↓
Generate upsell/bundle candidates
↓
Rank revenue opportunity
↓
Submit ONE proposal

10.3 Tools

get_cart()
search_products()
get_product()
check_inventory()
calculate_bundle()
submit_proposal()

submit_proposal() sends a proposal to AgentPay. It does not execute payment.

10.4 System prompt

Keep the merchant agent's system prompt in the repository and on the technical slide.

Conceptually:

You are the merchant revenue optimization agent. Maximize basket value using relevant bundles, upsells, and cross-sells. You may propose cart modifications, but you must never execute payment, modify authorization, or bypass AgentPay. Submit every proposal through AgentPay.

The prompt should be intentionally aggressive enough to create real pressure.

10.5 Proposal revision loop

The agent gets the gateway's block reason and may revise:

Proposal 1
↓
BLOCK + reason
↓
Read reason
↓
Proposal 2
↓
BLOCK + reason
↓
Proposal 3

Maximum 3 proposals.

After three failures:

Original cart retained

10.6 No-proposal path

If the merchant agent has nothing useful to propose:

Original cart
→ final hard re-validation
→ Razorpay

11. Intent Gate

11.1 What it is

The Intent Gate is not another agent.

It is one LLM classification call.

11.2 Inputs

Original buyer request
Signed intent from mandate
Original frozen cart
Proposed cart modification
Merchant proposal reason

11.3 Example

User:

Buy wireless earbuds under ₹3,000. No unnecessary accessories.

Merchant proposal:

Earbuds + protective case = ₹2,798

Intent gate:

{
  "decision": "BLOCK",
  "confidence": 0.94,
  "reason": "Accessory conflicts with signed user intent"
}

11.4 Authority model

The intent gate can:

allow a proposal that already passed hard checks

reject a proposal

trigger escalation

It cannot override a hard deterministic failure.

11.5 Confidence threshold

During Phase 7:

Create a small hand-labeled calibration set.

Select the confidence threshold.

Record the threshold in configuration.

Freeze it.

Do not tune it again after evaluation results are visible.

12. MCP Interface

Expose the merchant through the MCP Python SDK.

Required tools:

search_products()
get_product()
create_cart()
add_to_cart()
request_checkout()
complete_purchase()

MCP is a thin layer over backend endpoints that already work.

Therefore the build order is:

FastAPI
→ Catalog
→ Cart lifecycle
→ Cart freeze/hash
→ Razorpay
→ Webhooks
→ Public deployment
→ MCP wrapper

Do not build MCP first.

13. Razorpay Test Mode

Flow

AgentPay validates request
↓
Create Razorpay Test Mode order/payment flow
↓
Test checkout
↓
Payment result
↓
Webhook
↓
Reconcile
↓
Update order
↓
Audit event

The external AI agent drives the commerce transaction, but the actual payment interaction is handled by the application/Razorpay Test Mode checkout.

Do not claim the external model is independently typing card or UPI credentials.

14. Webhooks and Reconciliation

Webhook endpoint

Implement a FastAPI webhook endpoint.

Handle at minimum:

successful payment event

failed payment event

duplicate webhook delivery

unexpected state transitions

Validate webhook authenticity/signature according to Razorpay's Test Mode integration requirements.

Reconciliation

Maintain the relationship:

AgentPay transaction
↔ Razorpay order
↔ Razorpay payment
↔ final order status

Never let a stale or duplicate event silently produce a second financial action.

15. Idempotency and Duplicate Protection

Every payment-affecting operation should carry an idempotency key.

Test:

Request 1 → payment execution
Request 2 with same idempotency key
→ existing result / duplicate blocked

Also test the double-submit race during evaluation.

16. PostgreSQL Data Model

Minimum logical entities:

users
merchants
products
inventory
mandates
carts
cart_items
orders
transactions
audit_events

Mandate storage

Store:

mandate ID

signed payload

signature

status

expiry

consumed flag

Audit storage

Store:

event ID

mandate ID

event type

timestamp

payload hash

previous hash

current hash

decision

reason code

Use PostgreSQL + SQLAlchemy + Alembic.

17. Hash-Chained Audit Log

Each audit event references the previous event's hash.

Event 1
hash = A

Event 2
previous_hash = A
hash = B

Event 3
previous_hash = B
hash = C

This makes the log tamper-evident.

Important events include:

MANDATE_CREATED
MANDATE_VERIFIED
CART_CREATED
CART_FROZEN
UPSELL_PROPOSED
PROPOSAL_REJECTED
TRANSACTION_BLOCKED
ESCALATION_REQUIRED
CART_REVALIDATED
PAYMENT_CREATED
PAYMENT_CAPTURED
PAYMENT_FAILED
ORDER_UPDATED

A judge should be able to inspect why a transaction was allowed or blocked.

18. Merchant Storefront

Use one demo merchant: UrbanNest.

Products can include:

Wireless Earbuds — ₹2,499
Smart Watch — ₹3,499
Power Bank — ₹1,299
Protective Case — ₹299
Premium Bundle — ₹2,799

The storefront is a prop/test merchant.

Keep it small.

Do not build a full marketplace.

The important interface is the MCP/API, not the human-facing UI.

19. Evaluation Design

19.1 Two arms

Arm A — Cap-only

The system enforces the deterministic spending cap and hard policy constraints, but does not use signed-intent enforcement for merchant proposals.

Arm B — Intent-aware

The system uses:

hard constraints
+
signed intent
+
intent gate

Both arms use the same:

Merchant Revenue Agent

products

starting carts

buyer personas

persona prompts

19.2 Persona panel

Freeze the prompts before either arm runs.

Suggested personas:

price-sensitive

convenience-first

literal instruction follower

prompt-injected

Do not tune persona prompts after seeing results.

19.3 Sensitivity sweep

Run relevant assumptions under:

-30%
baseline
+30%

Do not change the evaluation architecture after observing the results.

20. Primary Metric — Mandate Ceiling Drift

Use:

[
\text{Ceiling Drift} = \frac{\text{Final Completed Spend}}{\text{Authorized Spending Cap}}
]

Denominator rule

Only completed transactions are included.

If a proposal is blocked and the buyer completes the original transaction, use that final completed spend.

If the buyer abandons, do not encode abandonment as ₹0 for ceiling drift.

Report abandonment separately.

This prevents the metric from being artificially improved by blocking all transactions.

21. Supporting Metrics

Measure:

legitimate purchase completion rate

abandonment rate

correct escalation rate

violations caught / attempted

replay protection rate

price-change protection

prompt-injection containment

duplicate-payment protection

The strongest quantitative evidence is the Cap-only vs Intent-aware ceiling-drift comparison with the same buyer/merchant behavior.

The adversarial suite is supporting evidence because the attacks were authored by you.

22. Adversarial Test Suite

Target approximately 30 scenarios.

Include:

1. Overspend
2. Cap splitting
3. Expired mandate
4. Replayed mandate
5. Wrong merchant
6. Wrong category
7. Price change after authorization
8. Cart modification after freeze
9. Duplicate checkout submit
10. Prompt injection
11. Currency mismatch
12. Unit confusion
13. Out-of-stock product
14. Merchant upsell
15. Duplicate payment race

Add additional variations until the suite is approximately 30 cases.

For each case record:

scenario_id
expected_outcome
actual_outcome
reason_code
model_invoked (yes/no)
latency
final_transaction_state

23. Failure Handling

Failure A — Overspend

Authorized: ₹3,000
Requested: ₹5,999

→ TRANSACTION_BLOCKED
→ LLM never invoked

Failure B — Merchant proposal conflicts with intent

Hard checks pass
→ intent gate rejects proposal
→ PROPOSAL_REJECTED
→ original cart continues

Failure C — Mandate replay

Single-use mandate already consumed
→ TRANSACTION_BLOCKED

Failure D — Cart manipulation

Frozen hash != final cart hash
→ TRANSACTION_BLOCKED

Failure E — Ambiguous intent

Low confidence
→ ESCALATION_REQUIRED
→ BLOCK until human decision

24. Merchant Console

Keep the dashboard thin.

Transaction view

Show:

buyer

original buyer request

signed mandate

original cart

merchant proposal

intent decision

policy decision

Razorpay state

Decision trace

Example:

Hard checks → PASS
Merchant proposal → ₹2,798
Intent gate → BLOCK
Reason → accessory conflicts with signed intent
Original cart → retained
Payment → completed

Audit viewer

Show:

event

timestamp

decision

reason

previous hash

current hash

25. Exact 7-Day Calendar

Day 1 — Sunday, 23 Aug

Security foundation

Ship:

failing tamper test

mandate schema

canonicalization

Ed25519 sign/verify

deterministic mandate verification

PostgreSQL

audit hash chain

Do NOT build

Claude

MCP

Razorpay

LangGraph

frontend polish

Acceptance

Tampered mandate is rejected and audited.

Day 2 — Monday, 24 Aug

Morning

FastAPI

catalog APIs

UrbanNest data

cart lifecycle

Afternoon

request_checkout

cart freeze

SHA-256 cart hash

deterministic policy engine

idempotency

Evening

Razorpay Test Mode

webhooks

reconciliation

audit integration

public deployment

Acceptance

A valid AgentPay transaction can reach Razorpay Test Mode and return through the webhook into PostgreSQL/audit.

Day 3 — Tuesday, 25 Aug

FREEZE POINT

Build:

MCP server

MCP tools

Claude connection

end-to-end external buyer flow

Required demonstration:

Claude
→ MCP
→ AgentPay
→ Razorpay Test Mode
→ Webhook
→ Order

Record a basic working backup immediately.

Once this works, the core submission exists.

Day 4 — Wednesday, 26 Aug

Merchant Revenue Agent

Build one LangGraph agent.

Implement:

analyze cart

search products

check inventory

generate offers

rank opportunity

submit proposal

reason-aware revision

max 3 proposals

original-cart fallback

no-proposal path

Store and document its system prompt.

Day 5 — Thursday, 27 Aug

Morning

Build intent gate.

Calibrate and freeze confidence threshold.

Afternoon

Build:

fail-closed behavior

human escalation

final deterministic re-validation

distinct reason-code families

proposal-rejected vs transaction-blocked semantics

Day 6 — Friday, 28 Aug

Morning

Freeze buyer persona prompts.

Run:

Cap-only arm

Intent-aware arm

adversarial suite

sensitivity sweep

Calculate:

ceiling drift

completion

abandonment

escalation

supporting security metrics

Afternoon

Build thin console.

Evening

Prepare failure demos.

Record the complete demo and backup.

Day 7 — Saturday, 29 Aug

Use only for:

bug fixes

final metrics

limitations

screenshots

slides

rehearsal

buffer

Do not introduce major features.

26. Tiered Priority System

Tier 1 — Submission-critical

These must never slip:

Signed mandates
Deterministic hard checks
Cart freeze/hash
Idempotency
Razorpay Test Mode
Webhooks
Public backend
MCP
Claude end-to-end
Audit trail

Tier 2 — Differentiators

Merchant Revenue Agent
Intent Gate
3-proposal revision loop
Human escalation

Tier 3 — Evidence

Cap-only vs Intent-aware
Ceiling drift
Abandonment
Escalation
Adversarial suite
Sensitivity sweep

Tier 4 — Polish

Dashboard
Animations
Fancy UI
Extra visualizations

If time gets tight, cut Tier 4 first.

Never sacrifice Tier 1.

27. Final Tech Stack

Frontend

React + Vite + Tailwind CSS

Core backend

Python + FastAPI

Database

PostgreSQL

ORM

SQLAlchemy

Migrations

Alembic

External AI buyer

Claude

Agent protocol

MCP Python SDK

Merchant Revenue Agent

LangGraph + LLM API

This is the only place LangGraph is used.

Intent Gate

LLM structured output + Python

Not a separate agent.

Authorization

Custom Python deterministic policy engine

Signing

Ed25519

Hashing

SHA-256

Audit

PostgreSQL + hash chain

Payments

Razorpay Test Mode

Webhooks

FastAPI

Evaluation

Python + pandas

Deployment

Vercel + Render/Railway

28. Technologies Explicitly Cut

Do not add these unless an actual concrete requirement appears:

LangChain

Redis

Kafka

Socket.IO

MongoDB

microservices

x402

crypto rails

voice

multi-merchant marketplace

custom ML model

giant e-commerce frontend

The project does not need technology for technology's sake.

29. Demo Flow — 5 Minutes

0:00–0:30 — User intent

User tells Claude:

"Buy good wireless earbuds under ₹3,000. No unnecessary accessories."

0:30–1:15 — Discovery

Claude uses MCP:

search_products()
get_product()
create_cart()

1:15–2:00 — Merchant pressure

Merchant Revenue Agent proposes an upsell.

Show the revision loop if needed.

2:00–2:45 — Authorization decision

Show:

signed intent

proposal

intent decision

reason code

audit event

2:45–3:30 — Attack

Prompt-inject Claude to exceed the user's cap.

Show:

Hard constraint failed
→ transaction blocked
→ LLM intent gate not invoked

3:30–4:15 — Payment

Complete a valid Razorpay Test Mode payment.

Show webhook confirmation.

4:15–5:00 — Proof

Show:

real ceiling-drift result

completion rate

abandonment rate

escalation rate

audit chain

30. Presentation Structure

Slide 1 — Problem

AI agents can buy, while merchants are incentivized to increase basket value.

Slide 2 — AgentPay

Show the architecture.

Slide 3 — Security boundary

Hard checks
→ Merchant proposal
→ Intent gate
→ Re-validation
→ Razorpay

Slide 4 — External AI commerce

Claude → MCP → UrbanNest.

Slide 5 — Merchant pressure

Show the merchant agent attempting an upsell.

Slide 6 — Gateway decision

Show proposal rejected or allowed, with reason code.

Slide 7 — Payment

Razorpay Test Mode + webhook.

Slide 8 — Evaluation

Cap-only vs Intent-aware ceiling drift.

Also show abandonment and escalation.

Slide 9 — Limitations

Be precise about what is and is not implemented.

31. Limitations / Honesty Rules

Never claim UAP implementation or conformance without a public specification you can actually validate against.

Use wording such as:

AP2-style mandate concepts and an ACP-shaped commerce interface are used as design references. UAP is not claimed as implemented; where relevant, the design is forward-looking rather than a conformance claim.

Never claim the gateway is universally secure.

Say:

The system was evaluated against the tested attack classes and failure scenarios.

Never claim Claude directly enters card/UPI credentials.

Say:

Claude drives the commerce transaction through MCP; Razorpay Test Mode handles payment execution.

Never invent evaluation numbers.

The only numbers that go into the final deck are numbers produced by the actual evaluation.

32. Commercial Answer

If a judge asks:

"Why would a merchant pay for something that can block revenue?"

Answer:

Agent commerce only scales if buyer agents can trust the merchants they transact with. A merchant that can prove it respects buyer mandates becomes easier for external agents to transact with, while fewer unauthorized agent purchases and disputes reduce downstream payment risk.

The product is therefore positioned as trust infrastructure for agentic commerce, not merely a blocker.

33. Final Pitch

Full version

AgentPay is a merchant-side authorization gateway for AI commerce. An external AI buyer can discover and transact with a Razorpay merchant, while a revenue-maximizing merchant agent pushes bundles and upsells toward the buyer's spending limit. AgentPay enforces the user's signed spending and intent mandate before any money moves, and we measure how much of that authorization merchant pressure captures with and without intent enforcement.

Spoken version

Claude buys. The merchant agent sells. AgentPay governs. Razorpay executes.

Core closing line

The merchant agent is optimized to maximize the cart. AgentPay is optimized to make sure the user still gets what they actually authorized.

34. Final Mental Model

Ignore all implementation detail when explaining the project informally.

USER
  │
  │ "Buy earbuds under ₹3,000.
  │  No accessories."
  ▼
CLAUDE
  │
  │ finds merchant
  ▼
AGENTPAY
  │
  │ hard checks
  │
  ├──────────────► MERCHANT REVENUE AGENT
  │                 │
  │                 │ propose / revise
  │                 ▼
  │              INTENT GATE
  │                 │
  │                 │ allow / block proposal
  │                 ▼
  └──────────────► AGENTPAY RE-CHECK
                         │
                         ▼
                      RAZORPAY
                         │
                         ▼
                      PAYMENT
                         │
                         ▼
                       AUDIT

Product

AgentPay

Agent you build

Merchant Revenue Agent

External buyer

Claude

Agent protocol

MCP

Authorization core

Signed mandate + deterministic policy + intent gate + cart integrity

Payment

Razorpay Test Mode

Core experiment

Cap-only vs Intent-aware Mandate Ceiling Drift

Core demo

External buyer → merchant pressure → AgentPay decision → Razorpay payment → audited result

35. Final Non-Negotiable Checklist

Before declaring the project complete, verify every item below.

Security

Tamper test passes

Ed25519 signing works

Signature verification works

Expired mandate is rejected

Replayed mandate is rejected

Wrong merchant is rejected

Wrong category is rejected

Overspend is rejected

Currency mismatch is rejected

Idempotency works

Cart integrity

Cart freezes at checkout request

Cart hash is stored separately from mandate

Frozen cart cannot silently change

Final re-validation works

Inventory is rechecked

AI

Claude is external buyer

MCP works

Merchant Revenue Agent is the only agent you build

Merchant agent uses LangGraph

Merchant agent has real tools

Merchant agent proposes, never executes

Maximum 3 proposals

Original cart fallback works

Intent gate is a classifier, not an agent

Intent gate fails closed

Confidence threshold is frozen

Payments

Razorpay Test Mode order creation works

Test payment flow works

Webhook verification works

Duplicate webhook handling works

Reconciliation works

Payment state reaches PostgreSQL

Audit

Every money-affecting decision is logged

Audit records are hash-chained

Reason codes distinguish transaction blocks from proposal rejection

Escalation is recorded

Evaluation

Persona prompts are frozen

Cap-only arm works

Intent-aware arm works

Ceiling drift uses completed transactions only

Abandonment is reported separately

Correct escalation rate is measured

Adversarial suite is executed

Sensitivity sweep is executed

No evaluation numbers are invented

Demo

Claude discovers UrbanNest

Claude builds a cart

Merchant agent proposes an upsell

Proposal can be rejected

Merchant agent can revise

Original cart can continue

Prompt-injection overspend is blocked

Valid payment reaches Razorpay Test Mode

Webhook is visible

Audit chain is visible

Real evaluation result is shown

Backup demo recording exists

36. FINAL COMMAND

Do not redesign the product after this point.

Start with:

1. Write the failing tamper test.
2. Build the mandate schema.
3. Implement Ed25519 signing and verification.
4. Set up PostgreSQL.
5. Implement the hash-chained audit log.

Then follow the phases in order.

The first true milestone is not the dashboard, not LangGraph, and not the merchant UI.

It is:

A one-byte change to a signed mandate must make the transaction invalid.

From there:

Mandate → Backend → Cart Freeze/Hash → Razorpay → Deploy → MCP → Claude → Merchant Agent → Intent Gate → Re-validation → Evaluation → Console → Demo.

Build the boundary first. Everything else exists to 