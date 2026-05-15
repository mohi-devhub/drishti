# Drishti — Build Plan

> 7 days. ~40-50 hours. Deadline: Sunday, May 17, 2026, 23:59 IST.

This document is the day-by-day sequence for building Drishti. It exists to remove decision fatigue during the build — every choice has been made in the design phase. This is the *order* in which to execute.

The plan is written for a solo build with Claude Code / Cursor as a collaborator. Each phase has a clear deliverable, a time budget, and an explicit "stop and validate" checkpoint.

---

## Current finish checklist

Updated: Friday, May 15, 2026.

Use this section as the source of truth for what remains before submission. The day-by-day plan below is historical planning context.

### Done

- [x] Core v0 backend is implemented: connector abstraction, normalized schema, provenance, cited chat, agent run log, findings API.
- [x] Cited chat is implemented with OpenAI tool use when `OPENAI_API_KEY` is configured, plus deterministic citation validation/fallback.
- [x] Agent is implemented and read-only: it proposes ops-saving actions and stores run logs/findings without external writes.
- [x] Demo UI is implemented: dashboard, cited chat, findings page, evidence drill-down, proposed-action rendering.
- [x] Clerk sign-in/sign-up and protected Next.js routes are implemented.
- [x] Clerk JWT template `drishiti` is configured for the demo merchant UUID claim.
- [x] Local demo merchant switcher exists for reviewer exploration.
- [x] Scale harness exists and has a committed report.
- [x] Supabase/Postgres integration is implemented through SQLAlchemy/asyncpg.
- [x] Implementation commits are pushed through Clerk auth and UI polish.
- [x] Demo seed expansion is implemented: Merchants A/B/C now get larger baseline order volumes plus RTO, delay, refund, and courier-margin scenarios, and the agent can produce findings for each merchant.

### Must finish for challenge submission

- [ ] Commit final `README.md` after reviewing it against the challenge rubric.
- [ ] Run one clean final smoke test:
  - [x] Seed demo data.
  - [x] Run the agent.
  - [x] Ask cited chat questions for revenue, RTO loss, and evidence behind findings.
  - [x] Verify Findings starts empty and populates only after `Run agent`.
  - [x] Verify Merchant A/B/C switching clears chat/findings state and does not leak stale UI data.
  - [ ] Verify signed-in Clerk flow reaches protected pages and backend calls use the configured JWT template. Protected-route redirects and token-fetch code path are verified; full signed-in browser automation still needs a Clerk testing token or manual signed-in browser check.
- [ ] Submit by replying to the email with the GitHub repo link.

### Production readiness P0

These are the first items to implement before calling Drishti production-ready.

- [ ] Remove the hard-coded `LOCAL_DEMO_JWT_SECRET`; require an explicit local demo secret and fail closed if absent.
- [ ] Keep `/demo/token/*` local-only and additionally fail closed unless an explicit demo-secret flag is configured.
- [ ] Gate HS256 demo-token verification to `DRISHTI_ENV=local`; production must use Clerk/JWKS only.
- [ ] Resolve Shopify webhook merchant from the authenticated shop domain/connection record, not an `x-drishti-merchant-id` request header.
- [ ] Hide or disable the merchant switcher for signed-in Clerk users; keep it only for local/demo reviewer mode.
- [ ] Add server-side user-to-merchant membership mapping for production: Clerk user/org -> `merchant_id`, with no browser-selected tenant trust.
- [ ] Add PII redaction or permission gating for raw source-record payloads before showing them in the browser.
- [ ] Tighten CORS to explicit methods and headers.
- [ ] Make `DATABASE_URL` required in non-local environments.
- [ ] Add per-merchant rate limits for `/chat` and `/agents/.../runs`.
- [ ] Refactor request-scoped DB transactions so reads and long OpenAI calls do not hold a transaction for the full HTTP request.
- [ ] Move agent run execution to Arq with `run_id` polling; add server-side idempotency for duplicate run requests.

### Production readiness P1

- [ ] Initialize and verify the Redis/Arq pool in API lifespan so webhook enqueue paths never silently no-op.
- [ ] Set explicit DB pool size, overflow, and timeout values.
- [ ] Add `/health/live` and `/health/ready`; ready should verify DB, Redis, and Alembic revision.
- [ ] Add request ID / correlation ID middleware and propagate IDs into Arq jobs.
- [ ] Log OpenAI failures to Logfire and return a typed status such as `openai_error` when falling back.
- [ ] Add retry/backoff around OpenAI calls.
- [ ] Add structured JSON stdout logging fallback even when Logfire is disabled.
- [ ] Add CI for backend tests, lint, frontend lint/typecheck, frozen lockfiles, and migration dry-run.
- [ ] Add dependency audit checks (`pip-audit`, `pnpm audit`) before production release.
- [ ] Add a staging deployment stanza with separate DB and Clerk instance.
- [ ] Add Supabase backup/PITR notes and a restore drill target.
- [ ] Add SLO targets to README: chat P95, agent run duration, ingestion lag.
- [ ] Ignore or explicitly commit installed `.agents/skills/*`; do not leave skill directories untracked.

### Demo polish P1

- [ ] Replace the lower-left generic issue pill with an inline/top-of-page error message that names the failing service and has retry.
- [ ] Tie the environment indicator to `/health`: green only when API health passes; otherwise grey/red.
- [ ] Render unknown metrics as `-`, not `0`, when API data has not loaded or failed.
- [ ] Add skeleton/loading states for dashboard and findings metrics.
- [ ] Add clear CTAs in empty states: chat prompts, dashboard/finding `Run agent`.
- [ ] Standardize currency display to `₹`, not mixed `Rs` and `₹`.
- [ ] Add domain title casing for acronyms: COD, RTO, AWB, SLA.
- [ ] Improve citation interaction: use subtle underline/click-to-pin evidence instead of only `title`.
- [ ] Add accessible labels and better focus contrast for icon-only controls.
- [ ] Respect `prefers-reduced-motion` for chat loading dots.
- [ ] Add branded `not-found.tsx` and `error.tsx`.

### Product depth P2

- [ ] Add streaming/SSE chat so tool calls and partial answer states render while work is running.
- [ ] Persist and resume chat sessions across reloads with a history/sidebar.
- [ ] Add a collapsible "show tool calls" panel for assistant messages.
- [ ] Improve aggregate evidence detail to show contributing order/shipment IDs, not only derived aggregate rows.
- [ ] Add finding filters/sort/search and URL state for selected finding/current merchant/chat session.
- [ ] Add finding lifecycle states: open, acknowledged, actioned, dismissed.
- [ ] Add finding deduplication fingerprints across runs.
- [ ] Add agent cancel support and per-merchant duty configuration.
- [ ] Add copy/share/export actions for findings.
- [ ] Add Playwright E2E tests for cited chat, run-agent flow, and merchant switching.
- [ ] Add a real 1k-merchant load test against the staging DB.

### Production/demo gaps to state clearly

- [x] Real user auth is implemented with Clerk for the web app.
- [x] Production tenant switching is not implemented. The visible Merchant A/B/C switcher is a demo-only affordance. In production, a merchant user should land in their own workspace and should not freely switch tenants unless they are an internal admin or belong to multiple Clerk Organizations with an explicit org-to-merchant mapping.
- [ ] Live OAuth/setup screens for Shopify, Shiprocket, and Razorpay are not complete. The connector abstraction exists; demo uses seeded/fixture data.
- [x] Supabase is used as Postgres via SQLAlchemy/asyncpg, so Supabase API metrics can show zero even when the database is active.
- [x] Findings proposed actions are read-only, which matches the brief. No external action execution exists.

### Nice to have

- [ ] Add a small chat debug/status indicator showing `OpenAI tool loop + citation validator`.
- [ ] Improve aggregate evidence detail to show contributing order/shipment IDs, not only the derived aggregate row.
- [ ] Add screenshots or a short demo flow section to `README.md`.
- [x] Add deployment notes for Railway/Vercel env vars to `README.md`.
- [ ] Run one hosted deployment smoke if deploying publicly before submission.

### Next implementation order

1. Run the clean final smoke test from the challenge checklist.
2. Update `README.md` with smoke-test results, current auth status, demo-only merchant switcher note, deployment envs, eval honesty, and production-readiness caveats.
3. Commit `README.md` last.
4. Push `main` and submit the repo URL.
5. After submission, start production hardening from the P0 list above.

---

## Constraints driving the sequence

- **Citations are the highest-risk feature.** If the validator doesn't work end-to-end, the demo collapses. Build it on Day 3 against fake data so we have time to debug.
- **Connectors are the highest-volume work.** Three of them, each with auth + 2-4 syncers. Spread across Days 2-4.
- **The agent depends on linked, normalized data.** Cannot build until at least one merchant's data is flowing through. Days 4-5.
- **The frontend is leverage-positive but not strictly required.** Can be deferred if the deadline tightens. Day 6 is the budgeted frontend window.
- **README must reflect ground truth.** Final day is for the README, real load harness numbers, and final polish.

---

## Day 0 — Setup (3-4 hrs, Sunday May 10 evening)

The "before the sprint" day. If you can carve a few hours tonight, the rest of the week feels easier.

**Deliverables:**
- [ ] GitHub repo created (`drishti`), public, with README skeleton.
- [ ] All 7 design docs (this file + 6 others in `docs/`) committed in the first commit.
- [ ] `pyproject.toml` with FastAPI, Arq, httpx, pydantic, alembic, openai, logfire, supabase pinned to current stable versions. Run `uv sync`.
- [ ] `web/` Next.js app initialized with `pnpm create next-app@latest --typescript --tailwind --app`; pin the exact version installed.
- [ ] Supabase project created; `.env.local` template committed (without keys).
- [ ] Railway project created with three services placeholder: `web`, `worker`, `redis`.
- [ ] Clerk app created, JWT template configured for `merchant_id` claim.
- [ ] Logfire project created, write token in `.env`.

**Stop and validate:**
- `make dev` brings up FastAPI + Arq worker + Next.js locally.
- `/health` returns 200.
- A request to `/health` shows up in Logfire's live view.

If this stalls past 4 hours, take the `recommend_claude_apps` recommendation — Claude Code in your terminal can scaffold this entire setup in 30 minutes.

---

## Day 1 — Foundation (Monday May 11, ~7 hrs)

The day where nothing demos but everything else depends on it.

### Phase 1.1 — DB schema + migrations (3 hrs)

- [ ] Translate `SCHEMA.md` § 2-6 into `alembic` migrations.
- [ ] Create `0001_init_merchants.py` through `0013_init_immutability_triggers.py`.
- [ ] Run migrations against Supabase. Verify in Supabase's table view.
- [ ] Add a few seed inserts for `merchants` (3 test merchants: `merchant_a`, `merchant_b`, `merchant_c`).

### Phase 1.2 — Auth wiring (1.5 hrs)

- [ ] FastAPI middleware that extracts Clerk JWT, sets `app.current_merchant_id` on the Postgres session.
- [ ] `get_current_merchant_id` dependency for routes.
- [ ] Helper `set_merchant_context_for_worker(merchant_id)` for Arq workers.
- [ ] Test: a request without a JWT returns 401; with an invalid one, 401; with a valid one, the route can read the merchant's row from `merchants`.

### Phase 1.3 — RLS + isolation tests (1 hr)

- [ ] `tests/test_isolation.py` with the negative-omission test. The test should fail at this point because there's no data; replace assertions with "doesn't return cross-tenant rows" against seeded merchants once Phase 1.4 lands. Mark as TODO.

### Phase 1.4 — `source_records` + sync_runs scaffolding (1.5 hrs)

- [ ] `db/repositories/source_records.py` with `insert_raw`, `get_by_id`, `list_for_merchant`.
- [ ] `db/repositories/sync_runs.py` with `create`, `update_status`, `record_metrics`.
- [ ] Test: insert a fake raw record under `merchant_a`, verify it's readable as `merchant_a` and *not* readable as `merchant_b`.

**Stop and validate at end of Day 1:**
- DB has all tables.
- Auth flows work.
- A repository function for raw records exists.
- An isolation test exists and passes (even if a placeholder).

---

## Day 2 — Connector abstraction + Shopify (Tuesday May 12, ~7 hrs)

### Phase 2.1 — Base abstractions (2 hrs)

- [ ] `connectors/base/transport.py` — `Transport` protocol, `LiveTransport`, `MockTransport`, `RecordingTransport`.
- [ ] `connectors/base/rate_limiter.py` — Redis-backed token bucket.
- [ ] `connectors/base/connector.py` — abstract `Connector` class.
- [ ] `connectors/base/resource_syncer.py` — abstract `ResourceSyncer` class with the generic `sync` loop.
- [ ] Test: `MockTransport` reads a fixture; `LiveTransport` honors the rate limiter.

### Phase 2.2 — Shopify connector (3.5 hrs)

- [ ] `connectors/shopify/connector.py` — auth (OAuth bearer), rate limiter (1.5 req/s).
- [ ] `connectors/shopify/syncers/orders.py` — `fetch_page` against the pinned Shopify Admin API version for the build, cursor extraction, normalize.
- [ ] `connectors/shopify/syncers/customers.py` and `products.py` — same pattern.
- [ ] Capture realistic Shopify fixtures using `RecordingTransport` against a Shopify dev store. Save to `fixtures/shopify/`.
- [ ] Sanitize PII in fixtures (replace real emails/phones with synthetic).

### Phase 2.3 — Sync workers + normalize jobs (1.5 hrs)

- [ ] `workers/sync_worker.py` — Arq job `sync_<source>_<resource>(merchant_id, cursor)`.
- [ ] `workers/normalize_worker.py` — Arq job `normalize_<source>(source_record_id)`.
- [ ] Wire the two-stage flow: sync writes to `source_records`, enqueues normalize.
- [ ] Test end-to-end: trigger a Shopify sync against fixtures, verify rows land in `orders`, `customers`, `products` with correct `raw_record_id` FKs.

**Stop and validate at end of Day 2:**
- Shopify orders/customers/products are flowing into normalized tables.
- Fixtures are committed; running the sync against fixtures completes in < 5s.
- One real Shopify dev store request via `LiveTransport` works (proving the pattern).

---

## Day 3 — Shiprocket + Razorpay + Citation Contract (Wednesday May 13, ~8 hrs)

### Phase 3.1 — Shiprocket connector (2 hrs)

- [ ] `connectors/shiprocket/connector.py` — API key auth with token refresh.
- [ ] `connectors/shiprocket/syncers/shipments.py` and `tracking.py`.
- [ ] Fixtures captured from Shiprocket sandbox or hand-crafted from API docs.

### Phase 3.2 — Razorpay connector (1.5 hrs)

- [ ] `connectors/razorpay/connector.py` — API key + secret, basic auth.
- [ ] `connectors/razorpay/syncers/payments.py`, `refunds.py`, `settlements.py`.
- [ ] Fixtures captured from Razorpay test mode.

### Phase 3.3 — `order_links` resolver (1 hr)

- [ ] `db/repositories/order_links.py` — `link_order_to_shipment`, `link_order_to_payment`.
- [ ] Trigger from normalize jobs after relevant inserts.
- [ ] Test: seed an order, shipment, and payment for `merchant_a`; verify `order_links` resolves correctly.

### Phase 3.4 — Citation contract (3 hrs)

This is the most leveraged 3 hours of the entire build.

- [ ] `chat/tools/registry.py` — define `ToolResult` typed shape with `rows`, `aggregates`, `provenance`.
- [ ] Implement 4 starter tools: `query_orders`, `rto_loss_by_pincode`, `query_shipments`, `query_payments`. Each returns the typed shape.
- [ ] `chat/citation_validator.py` — implement parse, existence, value-match, coverage, auto-attach.
- [ ] `chat/loop.py` — OpenAI tool-use loop with the validator wired in.
- [ ] System prompt in `chat/prompts/system.md` per `CITATION_CONTRACT.md` § 4.
- [ ] `tests/test_citation_validator.py` — corpus of 10-15 hand-crafted assistant outputs covering each pass + fail mode.

### Phase 3.5 — Smoke test (0.5 hrs)

- [ ] `POST /chat` with the seeded `merchant_a`'s data.
- [ ] Question: *"What's my total revenue this month?"* — verify the answer is cited and value-matches the underlying tool result.

**Stop and validate at end of Day 3:**
- All three connectors syncing against fixtures.
- `order_links` populated for the seeded merchants.
- Chat layer returns cited answers; uncited variants get redacted.
- Validator test suite passes.

---

## Day 4 — Agent + Webhooks + Tools breadth (Thursday May 14, ~7 hrs)

### Phase 4.1 — Agent base + first duty (2 hrs)

- [ ] `agents/base/agent.py` and `agents/base/duty.py`.
- [ ] `agents/rto_shipping_margin/agent.py` — the run loop.
- [ ] `agents/rto_shipping_margin/duties/cod_rto_risk.py` — the SQL detection + narration.
- [ ] `agents/rto_shipping_margin/narrator.py` — constrained LLM call with citation validation.
- [ ] Wire the read-only static check on agent surface.

### Phase 4.2 — Remaining three duties (2 hrs)

- [ ] `courier_margin_drift.py`
- [ ] `delayed_prepaid.py`
- [ ] `refund_shipping_mismatch.py`

Each follows the pattern: SQL detect → narration with citations → persist as `agent_findings`.

### Phase 4.3 — Agent triggers (0.5 hrs)

- [ ] Arq cron in `workers/agent_worker.py`.
- [ ] `POST /agents/rto_shipping_margin/runs` endpoint.
- [ ] Per-merchant staggering hash.

### Phase 4.4 — Shopify webhooks (1.5 hrs)

- [ ] `app/webhooks/shopify.py` — HMAC validation, idempotency table check, normalize enqueue.
- [ ] Test with Shopify CLI (or curl + valid HMAC).

### Phase 4.5 — Remaining chat tools (1 hr)

- [ ] `courier_margin_by_route`, `delayed_prepaid_orders`, `refund_shipping_mismatch_check`, `list_findings`, `get_finding`.
- [ ] Each follows the typed `ToolResult` shape.

**Stop and validate at end of Day 4:**
- Agent runs end-to-end on `merchant_c` (the stress merchant), produces findings.
- Findings appear in `agent_findings`; readable via the chat layer (`list_findings` tool).
- Shopify webhook works with a fake delivery.
- Chat can answer cross-tool questions: *"Which COD orders are losing money?"* gets a real, cited answer.

---

## Day 5 — Frontend + Demo polish (Friday May 15, ~7 hrs)

### Phase 5.1 — Chat UI (3 hrs)

- [ ] Next.js page at `/chat` with shadcn/ui.
- [ ] Chat input, message list, streaming-style render (or single-payload render given v0 doesn't stream).
- [ ] Citation rendering: `<cite>` markers → hoverable footnotes.
- [ ] "View raw" side panel that fetches `GET /api/source_records/{id}`.

### Phase 5.2 — Findings page (2 hrs)

- [ ] `/findings` page listing agent findings for the current merchant.
- [ ] Per-finding card: severity, savings range, narrative, evidence drill-down, proposed action.
- [ ] "Run agent now" button → `POST /agents/rto_shipping_margin/runs`, polls for completion, refreshes list.

### Phase 5.3 — Merchant switcher (1 hr)

- [ ] Clerk Organization-based switcher in the nav.
- [ ] Switching reveals only that merchant's data — demo of isolation.

### Phase 5.4 — Demo seed (1 hr)

- [ ] `scripts/seed_demo.py` — populates `merchant_a` (small, ~50 orders), `merchant_b` (medium, ~500 orders, mixed COD), `merchant_c` (stress, ~5k orders, deliberately seeded with RTO clusters and refund-mismatch cases).
- [ ] Trigger one full sync + agent run for each, so the demo opens with data ready.

**Stop and validate at end of Day 5:**
- Live demo URL on Railway works.
- Switching merchants shows different data.
- Asking *"Which couriers are costing me money?"* on `merchant_c` returns cited findings.
- Agent findings are visible and clickable to drill into evidence.

---

## Day 6 — Scale harness + observability + tests (Saturday May 16, ~7 hrs)

### Phase 6.1 — Load harness (2.5 hrs)

- [ ] `scripts/load_harness.py` for the README scale section.
- [ ] Run at N=100; capture `load_harness_report.md`.
- [ ] Run at N=1000 if time allows; otherwise extrapolate honestly.

### Phase 6.2 — Logfire integration polish (1 hr)

- [ ] Verify FastAPI auto-instrumentation is capturing every request.
- [ ] Verify OpenAI calls are captured (Logfire's OpenAI integration).
- [ ] Verify SQL queries are captured.
- [ ] Add custom spans for `agent_run`, `duty_detect`, `narrator_call`, `validator_pass`.
- [ ] Take screenshots of the trace tree for the README.

### Phase 6.3 — Test suite completion (2 hrs)

- [ ] `tests/test_isolation.py` — full coverage including the negative-omission test.
- [ ] `tests/test_citation_validator.py` — 30+ corpus entries.
- [ ] `tests/test_rate_limiter.py` — token bucket behavior.
- [ ] `tests/test_agent_tool_surface_is_readonly.py` — static check.
- [ ] `tests/test_source_records_append_only.py` — raw payload versions are never overwritten.
- [ ] `tests/test_sync_idempotent.py` — replay-same-cursor returns same rows.

### Phase 6.4 — Buffer for known issues (1.5 hrs)

Reserved for whatever is broken at this point. There will be something.

**Stop and validate at end of Day 6:**
- Load harness produces a real numbers table.
- Logfire shows complete traces.
- All tests pass.
- The system has been fully exercised against the seeded merchants.

---

## Day 7 — README + final polish (Sunday May 17, ~5-6 hrs, deadline 23:59)

This is the day where the README — the document the evaluator actually reads first — becomes ground truth.

### Phase 7.1 — README v1 (3 hrs)

Write the README with these sections, *all* drawing from real numbers and real file paths in the repo:

```markdown
# Drishti — AI ops analyst for D2C brands

[5-line architecture summary]

## What I built
[concrete capabilities, with paths to the relevant files]

## Connectors — why these three
[brief reasoning + link to docs/CONNECTORS.md]

## Schema — why this shape
[brief reasoning + link to docs/SCHEMA.md]

## Chat — the citation contract
[the contract in 5 sentences + link to docs/CITATION_CONTRACT.md]

## Agent — Drishti's first AI employee
[the framing + link to docs/AGENT.md]

## Scale — how this goes from 1 to 10k merchants
[what breaks first, what is built, what is sketched, and real load-harness output]

## Where Drishti breaks (eval honesty)
[honest list of known gaps from PRD, agent docs, connector docs, and actual test results]

## Hours spent
[honest tally per day]

## What I'd do with another week
[the list from docs/PRD.md § 8]

## A note on AI tools
[honest accounting of what Claude wrote vs what I wrote]
```

### Phase 7.2 — Final polish (2 hrs)

- [ ] Commit history review — cleanup, sensible messages.
- [ ] `.env.example` complete; secrets removed.
- [ ] `README.md` proofread.
- [ ] Demo URL pinned in README.
- [ ] Recording a 3-minute Loom walkthrough is optional but high-leverage if time remains.

### Phase 7.3 — Submit (0.5 hrs)

- [ ] Reply to the email with the GitHub repo URL.
- [ ] Send before 23:59 IST.

---

## Cuts to make if behind schedule

If at any point you're behind, here's the order to cut:

1. **Day 5 Phase 5.4 demo seed reduces scope** — `merchant_c` only, smaller volume.
2. **Day 6 Phase 6.1 load harness at N=100 only** — extrapolate to 10k in prose.
3. **Day 4 Phase 4.4 Shopify webhooks** — drop entirely; document as v1, polling is fine.
4. **Day 5 Phase 5.3 merchant switcher** — drop; demo with one merchant, document multi-tenant in prose.
5. **Day 5 frontend in general** — fall back to a Swagger demo + hosted load harness output. Costly but recoverable.
6. **Day 4 fourth duty (`refund_shipping_mismatch`)** — drop; agent has 3 duties, still meets brief.

Things that **do not get cut under any circumstance:**
- Citation validator (Day 3 Phase 3.4) — the demo collapses without it.
- At least one duty of the agent with a working narration (Day 4 Phase 4.1) — required by brief.
- Multi-merchant demo data (Day 5 Phase 5.4 minimal version) — required for the isolation test to be visible.
- README with eval honesty section (Day 7 Phase 7.1) — required by brief.

---

## A note on velocity

The plan front-loads the load-bearing risky work (foundations, citation contract, agent) and back-loads the visible polish (frontend, README). This is the opposite of the usual "demo-driven" build but right for an evaluator who scores judgment heavier than polish.

If you finish early, the leverage moves are: more validator corpus, more agent duties, live OAuth on Razorpay (closes a documented gap), or a chat-history persistence with conversation summaries.

If you finish late, the README's honesty section absorbs the gap. *"X is sketched, Y is partial, Z is documented as v1"* is the right voice when the alternative is hiding what didn't ship.
