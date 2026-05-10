# Drishti — Product Requirements Document

> *Drishti* (दृष्टि) — Sanskrit for *vision* / *insight*. The ops insight a D2C founder doesn't have time to stitch together.

## 1. What Drishti is, in one paragraph

Drishti is an AI operations assistant for D2C brands. It connects to Shopify, Shiprocket, and Razorpay; pulls every order, shipment, payment, and refund into one merchant-scoped database; and lets a founder ask cross-tool questions in chat — *"which orders are losing money?"*, *"which courier is causing the most RTOs?"*, *"are any prepaid shipments stuck past SLA?"* — and get answers where every number is traceable back to the literal API response that produced it. Alongside the chat, an autonomous worker — Drishti's first AI employee — runs daily, watches the same data, and proposes ₹-saving actions (prepaid-only rules for risky COD segments, courier swaps on margin-negative lanes, escalations on delayed prepaid). It does not execute actions in v0; it produces a run log of findings and recommendations, with reasoning and citations.

## 2. Who it's for

The Indian D2C founder running a 1–10 person company on Shopify, shipping via Shiprocket, collecting payments via Razorpay. They have:

- **Data scattered across 3+ SaaS dashboards** with no single view.
- **No analyst.** They open Excel exports when something feels off, then close them when it gets too painful.
- **Real money leaking** through RTO, courier inefficiency, and refund-shipping mismatches that no one has time to detect.
- **Distrust of black-box AI** for ops decisions involving real rupees.

Drishti is for them. The product promise is: *"Ask any question across your tools. Every number we give you is traceable to a real row in a real API response from a real timestamp. Every action we propose comes with the evidence."*

## 3. The five hard requirements (from the brief) and how Drishti satisfies each

| # | Requirement | Drishti's answer |
|---|---|---|
| 1 | At least 3 connectors behind one shared abstraction | `Connector` + `ResourceSyncer` + `Transport` protocol. Three implementations: Shopify, Shiprocket, Razorpay. Documented in `CONNECTORS.md`. |
| 2 | Universal data model with provenance on every row | Hybrid schema: domain-split tables (`orders`, `shipments`, `payments`, …) plus universal `source_records` raw JSONB store. Every row carries `source`, `source_record_id`, `raw_record_id` (FK), and `sync_run_id`. Documented in `SCHEMA.md`. |
| 3 | Chat layer with citation contract — uncited numbers don't survive | Tool-call-only citation model. The chat LLM cannot write numbers; it can only reference values from typed tool results. A validator enforces existence + value-match + coverage on every turn. Documented in `CITATION_CONTRACT.md`. |
| 4 | At least one autonomous agent | RTO + Shipping Margin Worker, four duties (COD-RTO risk, courier margin drift, delayed prepaid escalation, refund-shipping mismatch). Daily cron + manual trigger. Read-only by construction. Documented in `AGENT.md`. |
| 5 | Scalability layer for 1 → 10k merchants | Built: per-merchant RLS isolation + isolation tests, per-(connector, priority) Arq queues + token-bucket rate limiters, Shopify webhooks fully wired, cursor-based incremental sync everywhere. Sketched: rollup tables, multi-region, backfill. Summarized in this PRD and expanded in the README. |

## 4. Why these three connectors

The choice is judgment, not convenience. The connector trio has to cover the three pillars of D2C ops *with no overlap and no gaps*:

- **Shopify** — commerce truth: orders, customers, products, fulfillment status. Without this, there is no business.
- **Shiprocket** — shipping truth: courier assignment, freight, tracking events, RTO/delay signals. The single biggest unmonitored cost center for Indian D2C is shipping.
- **Razorpay** — money truth: payments, refunds, settlements. Without this, you cannot reason about margin.

The three together produce the joins where *insight lives*: a Shopify order has a Shiprocket shipment has a Razorpay payment, and the cross-source view is what no individual SaaS dashboard shows. Two of these alone are insufficient; four would be diminishing returns inside a 7-day v0.

We also chose Shopify over WooCommerce despite WooCommerce's larger Indian footprint. Shopify has cleaner OAuth, predictable response shapes, mature webhooks, and its dev-store free tier means we can prove a real live OAuth path during evaluation. The README will note the tradeoff.

## 5. Why one wide agent rather than several narrow ones

The brief frames the project as *"AI employees for D2C brands"*. An employee is one entity with multiple duties, not a collection of single-purpose detectors. Splitting into four narrow agents would tell a worse product story (a registry of toy detectors) and a worse engineering story (four cron jobs, four logs, four configurations). The wide-and-shallow Worker is one entity with four duties under a single run log — closer to how a human ops analyst actually thinks.

A risk we've internalized: wide agents can read as four shallow `if` branches if the run log doesn't show real reasoning. The mitigation, detailed in `AGENT.md`, is that each duty has its own typed `Finding`, evidence schema, and documented failure modes — the run log reads like four substantiated investigations, not four boolean checks.

## 6. v0 scope — what's in

- Full sync (Shopify orders/customers/products, Shiprocket shipments/tracking, Razorpay payments/refunds/settlements) for at least one demo merchant via captured fixtures, plus one live OAuth path (Shopify → dev store).
- Universal schema with provenance on every row, RLS-enforced multi-tenant isolation.
- Chat layer with read-only tools over the data, tool-call-only citation contract, full provenance drill-down in the UI.
- The RTO + Shipping Margin Worker, four duties, daily cron + manual trigger, read-only.
- Three seeded merchants in the demo, isolation test suite, load harness producing N=100 / N=1000 throughput numbers.
- Logfire observability across the FastAPI app, the Arq workers, and the OpenAI tool-call loop.
- Live deployment on Railway, evaluator-accessible URL, Clerk-gated login.

## 7. v0 scope — what's deliberately out (and why)

- **Action execution.** The brief says explicitly: *"don't actually send anything; we want the run log and the reasoning."* The agent's tool surface is read-only by construction (enforced at the tool-registry level — there is no tool that mutates external state). Action execution would be v1 work and is deferred.
- **Live OAuth on all three connectors.** Shopify is wired live as proof of pattern. Shiprocket sandbox is inconsistent and Razorpay test mode doesn't generate realistic settlement/refund flows; live OAuth on these would consume disproportionate hours for marginal demo value. The `Transport` protocol means the path is identical when keys are flipped to live; this is documented and demonstrable.
- **Webhooks on all three connectors.** Shopify webhooks are fully wired (HMAC validation, idempotency table, normalize-job enqueue). Shiprocket and Razorpay webhooks are documented in `CONNECTORS.md` with the same shape but not implemented in v0. We chose one real implementation over three half-broken ones.
- **Backfill of source_records older than the fixture window.** The schema supports it; the script is not built.
- **Rollup tables for hot aggregations.** Indexes are in place; rollups are a planned mitigation for query latency at higher scale, not built.
- **Multi-region or HA deployment.** Single-region Railway is the v0 target. Documented in the README's eval-honesty section.
- **A merchant-facing settings UI.** The chat is the UI in v0. Connection setup uses the `/connections` API directly and a simple form; no settings page beyond what's strictly necessary for the demo.

## 8. Demo strategy

Hybrid: real schema, mostly captured fixtures, one live OAuth path.

- **Shopify** — live OAuth flow proven against a Shopify dev store. The evaluator can connect a fresh dev store and watch a sync run end-to-end.
- **Shiprocket and Razorpay** — `MockTransport` replaying captured-and-sanitized real API responses from `connectors/{source}/fixtures/`. The same connector code paths run; only the transport differs. The README documents how to flip to live.
- **Three seeded merchants** — `merchant_a` (small, ~50 orders), `merchant_b` (medium, ~500, mixed COD/prepaid), `merchant_c` (stress, ~5000, deliberately seeded with RTO clusters and refund-mismatch cases). The evaluator can switch between them via the merchant switcher.

This was a judgment call: pure live OAuth on all three would have looked impressive at first glance but would have burned 8–12 hours fighting sandboxes for marginal gain over the things we're actually scored on. Pure fixtures would have looked lazy. Hybrid says: *"I know what looks impressive, and I optimized for what's actually being graded."*

## 9. Success criteria for v0

The v0 is successful if an evaluator, given the live URL and a 30-minute review window, can:

1. **Log in as one of three demo merchants** via Clerk, and *see different data per merchant*.
2. **Ask a cross-tool question in chat** ("which orders lost money this month?") and watch the answer arrive with hoverable citations that drill down to raw API responses.
3. **Trigger the agent manually** via the UI button or API endpoint and watch a structured run log appear with findings, evidence, ₹-savings estimates, and proposed actions — none of which fire externally.
4. **Open Logfire** (or the embedded run log view) and trace a single chat turn end-to-end: message → tool calls → SQL queries → citation validation → response.
5. **Run `scripts/load_harness.py`** and see real numbers for N=100 and N=1000 synthetic merchants.
6. **Read the README** and understand exactly what we built, what we deferred, what breaks first, and what we'd build next.

If all six work in 30 minutes, the v0 has done its job.

## 10. AI tool honesty (a v0 commitment)

The brief explicitly invites it: *"Use them. We expect you to. Be honest in the README about what you wrote vs. what the LLM wrote."*

The plan, to be tracked through the build and reported in the final README:

- **Architecture, schema, agent design, citation contract** — designed in collaboration with Claude over multiple rounds of pushback on each major decision (every choice in this PRD has a documented "why"). Trail of decision-making is preserved in chat history.
- **Boilerplate (FastAPI scaffolding, Pydantic schemas, Arq job stubs, Next.js pages)** — generated by Claude Code, reviewed and edited before committing.
- **SQL for agent duties, citation validator state machine, RLS policies, isolation tests** — written by hand because they're load-bearing for correctness and the evaluator will probe them.
- **Fixtures** — captured from real Shopify dev store / Shiprocket sandbox / Razorpay test mode using the `RecordingTransport`, then sanitized and committed by hand.
- **Tests** — written by hand for the load-bearing pieces (isolation, citation validator, agent failure modes); generated and reviewed for the rest.

The README will report the actual split with file-level honesty. This is signal, not stigma.
