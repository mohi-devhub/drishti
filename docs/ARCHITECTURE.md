# Drishti — Architecture

This document describes how Drishti is put together: every component, how they fit, and how data flows through three named paths (sync, chat turn, agent run). Schema details live in `SCHEMA.md`; connector internals in `CONNECTORS.md`; the citation contract in `CITATION_CONTRACT.md`; the agent in `AGENT.md`; product and scale framing live in `PRD.md`. This document is the map.

## 1. Five-line architecture summary

Drishti is a FastAPI service backed by Postgres (Supabase, with row-level security per merchant) and a Redis-backed Arq worker pool that runs scoped sync jobs and agent runs. Three connectors — Shopify, Shiprocket, Razorpay — share a layered abstraction (`Connector` + `ResourceSyncer`) and a swappable `Transport` (live HTTP or replayed fixtures). All API responses land first in an append-only raw store; an async normalizer then projects them into typed domain tables, every row carrying full provenance. A Next.js chat UI (Clerk-authenticated) talks to a tool-using OpenAI loop whose every numeric claim is validated against the underlying tool results before reaching the user. A daily Arq cron runs the RTO + Shipping Margin Worker — Drishti's first AI employee — which uses deterministic SQL to detect findings and a constrained LLM to narrate them, producing a read-only run log of proposed ₹-saving actions.

## 2. Tech stack (pin exact patch on init day)

| Layer | Choice | Notes |
|---|---|---|
| Language (backend) | Python 3.14 | Current stable Python line as of May 10, 2026 |
| Backend framework | FastAPI 0.136+ | Async, Pydantic-native, OpenAPI free |
| ORM / DB driver | SQLAlchemy 2.x async + asyncpg | Mature async support |
| Migrations | Alembic | SQLAlchemy-native |
| Database | Postgres via Supabase | Use the newest Supabase-supported major available on init day; otherwise use latest patch of a supported major |
| Queue | Arq (latest) + Redis 7 | Async-native, FastAPI-compatible |
| LLM provider | OpenAI: GPT-5.2 (chat + agent narration), GPT-5-mini (cheap calls) | Strong tool-use, structured outputs |
| Frontend | Next.js 16.2.x (latest patch from May 2026 security release) | App Router, RSC |
| UI components | shadcn/ui + Tailwind 4 | Standard, evaluator-friendly |
| Auth | Clerk | Sessions, orgs (= merchants), JWT to backend |
| Deploy | Railway | Single project: web + worker + Redis |
| Observability | Pydantic Logfire (Personal, free tier) | OTel-based, FastAPI + OpenAI auto-instrumentation |
| Testing | pytest + pytest-asyncio | Sync code paths and async |
| Lint/format | ruff + black | Latest |

Frontend npm runs against `next@latest react@latest`; backend pins are in `pyproject.toml` with exact versions resolved on init day. The README's stack section will list the pinned versions actually shipped.

## 3. System components

### 3.1 Web (FastAPI)

Stateless HTTP layer. Endpoints group into:

- **`/auth/*`** — Clerk webhook handlers for org/user lifecycle (org = merchant).
- **`/connections/*`** — OAuth callbacks and connection management (Shopify, Shiprocket, Razorpay).
- **`/webhooks/{source}/*`** — inbound webhooks. Shopify HMAC-validated; Shiprocket/Razorpay endpoints exist but no-op in v0 (documented).
- **`/chat/*`** — chat session and turn endpoints; runs the tool-using OpenAI loop with citation validation.
- **`/agents/*`** — manual agent trigger (`POST /agents/{merchant_id}/runs`), run-log read endpoints.
- **`/admin/*`** — internal endpoints for the load harness and isolation tests; production-disabled.

Every endpoint that touches merchant data goes through a middleware that resolves `merchant_id` from the Clerk session and sets `app.current_merchant_id` for the duration of the request, which RLS keys off.

### 3.2 Worker (Arq)

Three logical worker pools, deployed as separate Arq processes on Railway for isolation:

- **`sync_worker`** — runs `sync_*` jobs (one per connector resource). Reads cursor, fetches a page, writes to `source_records`, enqueues normalize jobs.
- **`normalize_worker`** — consumes normalize jobs. Reads raw JSONB by `raw_record_id`, runs source-specific `Normalizer`, upserts into domain tables.
- **`agent_worker`** — runs the RTO + Shipping Margin Worker. Daily cron (per merchant, staggered) plus on-demand triggers.

Queues are partitioned by `(connector, priority)`: `q:shopify:high`, `q:shopify:bulk`, `q:shiprocket:high`, etc. Per-merchant work hashes consistently into the right queue so one merchant cannot starve another. Token-bucket rate limiters (Redis-backed for cross-worker coordination) wrap each connector's HTTP client at published API limits.

### 3.3 Database (Supabase Postgres)

The schema is listed in `SCHEMA.md`. Every tenant-owned table carries `merchant_id` as the first column with a compound index starting on it. RLS policies on every table enforce `merchant_id = current_setting('app.current_merchant_id')::uuid`.

The DB also stores: connection credentials (encrypted at the application/Vault layer before persistence), webhook delivery idempotency, sync run logs, agent run logs, chat history, and tool-call audit logs. Nothing persistent lives outside Postgres in v0.

### 3.4 Frontend (Next.js)

App Router. Three core pages:

- **`/`** — merchant switcher (gated by Clerk; multi-org users see all their merchants).
- **`/chat`** — the conversation UI. Streaming responses, hoverable citation footnotes, drill-down panel that shows the cited domain row and the underlying raw API response.
- **`/agent`** — the agent run log: list of runs, expandable findings, evidence rows with citations, proposed-action display.

The frontend talks only to the FastAPI backend over JWT-authenticated HTTPS. No direct Supabase reads from the client; every read goes through tools that respect merchant scope.

### 3.5 LLM layer

OpenAI's chat completions API with tool calls. Two distinct loops:

- **Chat loop** (in the web process): handles a user turn, streams reasoning, calls read-only tools, runs the citation validator on the assembled response before streaming the final answer.
- **Agent narration loop** (in the agent_worker): given a structured `Finding` produced by deterministic SQL, asks the LLM to write the narrative + proposed action, runs the same citation validator on the output.

Both loops use the same tool-result schema (typed rows + aggregates with IDs) and the same `<cite>` marker grammar. Both loops are instrumented in Logfire with the OpenAI auto-instrumentation, so every LLM call is visible as a span tree.

### 3.6 Observability (Logfire)

Auto-instrumented:

- FastAPI requests (route, status, latency, merchant_id attribute)
- SQLAlchemy queries (statement, duration)
- OpenAI calls (model, prompt, tokens, tool calls, latency)
- Arq jobs (queue, function, args, duration, status)

Manually instrumented:

- `agent_run` span wrapping a full agent run, with child spans per duty
- `tool_call` span around every chat-layer tool invocation
- `citation_validation` span recording pass/fail per claim
- `sync_run` span per connector resource with cursor and counts

The README will include screenshots of the Logfire flame view showing one chat turn end-to-end.

## 4. Path 1: Sync flow (per resource, per merchant)

```
Arq cron / webhook                                           Postgres
  │                                                              ▲
  │ enqueue sync_<source>_<resource>(merchant_id)               │
  ▼                                                              │
sync_worker                                                       │
  │                                                              │
  │ load Connection (creds, cursor)                              │
  │ build Connector(transport=Live|Mock)                          │
  │ build ResourceSyncer(connector, resource)                     │
  │                                                              │
  │ loop:                                                         │
  │   page = await syncer.fetch_page(cursor)    ◄─ rate-limited  │
  │   for record in page:                                         │
  │     write source_records (raw JSONB) ─────────────────────►──┤
  │     enqueue normalize(source, source_record_id)              │
  │   cursor = syncer.cursor_from(page)                           │
  │   save cursor on Connection ─────────────────────────────►──┤
  │ end loop                                                      │
  │                                                              │
  │ write sync_runs row (status, counts, errors) ─────────────►──┘
```

Stage 1 (sync) only ever writes raw. It is idempotent w.r.t. our schema: even if our normalization breaks tomorrow, the raw bytes are safe.

```
normalize_worker
  │
  │ load source_records row by raw_record_id
  │ select Normalizer for (source, resource_type)
  │ run normalizer → typed domain row
  │ upsert into orders / shipments / payments / ... with raw_record_id FK
  │ if cross-source identifier present, upsert order_links
  │ done
```

Stage 2 (normalize) is replayable: re-run the worker over `source_records` and rebuild domain tables without touching external APIs.

`order_links` is the table that makes cross-tool questions answerable. When normalizing a Shiprocket shipment we look up the Shopify order it references (Shiprocket carries `order_id` in its payload) and create or update the link row. Same for Razorpay payments referencing Shopify order IDs.

## 5. Path 2: Chat turn flow

```
User types "which COD orders lost money this month?"
       │
       ▼
Next.js → POST /chat/turns ──► FastAPI
                                    │
                                    │ resolve merchant_id from Clerk JWT
                                    │ set app.current_merchant_id (RLS gate)
                                    │ load chat history for session
                                    │
                                    ▼
                              OpenAI tool-use loop
                                    │
                                    ├─► tool: query_rto_losses(date_range)
                                    │     │
                                    │     │ deterministic SQL (no LLM)
                                    │     │ returns:
                                    │     │   { result_id: "tr_5d8f",
                                    │     │     rows: [{row_id, values, source, raw_record_id, ...}],
                                    │     │     aggregates: [{agg_id, label, value, derived_from_row_ids}] }
                                    │     ◄
                                    │
                                    ├─► (optional) tool: drill_down(row_id)
                                    │     │
                                    │     │ resolves to raw_record_id → source_records JSONB
                                    │     ◄
                                    │
                                    │ model produces draft response
                                    │   "COD orders to pincode 1100XX
                                    │    lost ₹3,960<cite agg_a91> over 12<cite ...> orders."
                                    │
                                    ▼
                              Citation validator
                                    │
                                    │ for every numeric token:
                                    │   - is it inside a <cite> tag? (coverage)
                                    │   - does the cited agg_id/row_id exist in this turn's tool results? (existence)
                                    │   - does the cited value equal the model's number? (value-match)
                                    │
                                    │ if pass: convert <cite> to UI footnote markup, send
                                    │ if fail (first time): re-ask model with structured feedback (one retry)
                                    │ if fail (second time): redact uncited numbers as [uncited], surface warning chip, log to tool_calls.validation_failures
                                    │
                                    ▼
                              Stream to client
                                    │
                                    ▼
                              Next.js renders with footnotes + drill-down panel
```

Every step is logged: the chat turn, every tool call, every SQL query, every citation validation pass/fail. The `tool_calls` table is the durable record; Logfire is the live view.

## 6. Path 3: Agent run flow

```
Arq cron (03:00 IST, staggered by hash(merchant_id) over 4 hours)
       │  OR
Manual: POST /agents/{merchant_id}/runs
       │
       ▼
agent_worker
       │
       │ create agent_runs row (trigger=scheduled|manual, status=running)
       │
       │ check freshness: last successful sync per source < 6h?
       │   no → log skipped_stale per duty, continue with available sources
       │
       ▼
For each duty (cod_rto_risk, courier_margin_drift, delayed_prepaid, refund_shipping_mismatch):
       │
       │ Stage 1 — Deterministic detection
       │   run duty's parameterized SQL
       │   produces 0..N candidate Findings, each with:
       │     - finding_type
       │     - evidence_row_ids (the cited domain rows)
       │     - estimated_saving_inr (deterministic, with stddev for range)
       │     - severity (computed from evidence count + impact)
       │   if evidence_row_ids.length < 5: downgrade or suppress
       │
       │ Stage 2 — LLM narration (constrained)
       │   for each Finding:
       │     prompt LLM with structured Finding + tool-result-shaped evidence
       │     LLM produces: narrative, proposed_action (structured), confidence
       │     run citation validator on narrative (same as chat layer)
       │     if validation fails twice: store with narrative_status=degraded, structured-only view
       │
       │ persist agent_findings rows with citations
       │
       │ update agent_runs (status=completed, finished_at, duties_run, error counts)
       ▼
Findings visible in /agent UI; queryable via chat tools
```

The agent's tool surface is read-only by construction: it uses a separate tool registry (`AGENT_TOOLS`) that contains only deterministic SQL queries and the LLM narration call. There is no tool that mutates external state. This is enforced at the registry level and tested.

## 7. Tenant isolation — defense in depth

Every layer enforces merchant scope independently. A bug in any one layer cannot leak data because the layer below catches it.

1. **Clerk session → merchant_id resolution.** Clerk org membership defines which merchants a user can access. The middleware refuses to set `app.current_merchant_id` if the requested merchant is not in the user's org list.
2. **Application-layer filter.** Every repository function takes `merchant_id` as the first argument and adds `WHERE merchant_id = ?` to its query. Code review checks this.
3. **Postgres RLS.** Every table has a policy `USING (merchant_id = current_setting('app.current_merchant_id')::uuid)`. Even if step 2 forgets the filter, RLS rejects the row.
4. **Tool schemas omit merchant_id.** The chat LLM and the agent LLM cannot specify `merchant_id` in tool arguments. The backend injects it from the session. The model has no surface area to request another merchant's data.
5. **Cross-tenant test suite** (`tests/test_isolation.py`): for every domain table, attempts a read while authenticated as a different merchant. Asserts zero rows. Includes a "negative test" that deliberately removes the application-layer filter and asserts RLS still prevents the leak.

## 8. Configuration and secrets

- **Clerk keys, OpenAI key, Supabase service-role key, Logfire token** — Railway environment variables, never committed.
- **Per-merchant connection credentials** (Shopify access token, Shiprocket auth token, Razorpay key/secret) — stored in `connections` table after app-level envelope encryption or Supabase Vault storage; database encryption at rest is not the only protection.
- **`.env.example`** committed with all variables, no values.
- **Demo merchant credentials** — fixtures-only by default; the README notes how to bring your own keys to flip Shopify to live.

## 9. Deployment topology (Railway)

One Railway project, four services:

| Service | What runs | Scale |
|---|---|---|
| `web` | FastAPI (uvicorn) | 1 instance v0; horizontal at scale |
| `sync-worker` | Arq worker, queues `q:*:high` and `q:*:bulk` | 1 instance v0 |
| `agent-worker` | Arq worker, queue `q:agent` + cron scheduler | 1 instance v0 |
| `redis` | Managed Redis 7 | 1 instance |

Postgres lives at Supabase (separate provider). Frontend (Next.js) deploys to Vercel and points at the Railway web service. Logfire is a managed external service.

The README will include a one-line `docker-compose.yml` walkthrough for local dev parity.

## 10. What this architecture optimizes for

In priority order:

1. **Tenant isolation correctness.** Three independent layers; missing any one is still safe.
2. **Citation contract integrity.** No path from "model wrote a number" to "user saw it" without lineage.
3. **Replayability.** Raw immutable store + idempotent normalizers means the worst class of bugs (corrupted normalized data) is recoverable.
4. **Connector swappability.** New connector = `Connector` subclass + N `ResourceSyncer` subclasses + fixtures. No other code changes.
5. **Demo determinism.** Fixtures-by-default means the evaluator's experience does not depend on a flaky third-party sandbox.

In deliberate non-priorities for v0:

- Performance optimization beyond what indexes give us (rollups deferred).
- Multi-region availability.
- Action execution.
- Connector breadth (three is enough; the abstraction proves four would be straightforward).

## 11. Glossary

- **Merchant** — a single D2C brand, the tenant unit.
- **Connection** — a merchant's authenticated link to one source SaaS (one merchant has up to three connections in v0).
- **Source** — one of `shopify | shiprocket | razorpay`.
- **Source record** — one raw, immutable JSON response (or response item) from a source API. Lives in `source_records`.
- **Sync run** — one execution of a sync job for one (merchant, connector, resource) tuple. Recorded in `sync_runs`.
- **Domain row** — a typed row in `orders`, `shipments`, `payments`, etc., produced by normalizing a source record.
- **Tool result** — the structured payload a chat-layer or agent-layer tool returns: rows + aggregates, all with IDs.
- **Citation** — a `<cite agg_id|row_id>` marker in model output. Resolves through the validator to a domain row → raw_record_id → source API call + timestamp.
- **Duty** — one of the four detection paths the agent runs (`cod_rto_risk`, `courier_margin_drift`, `delayed_prepaid`, `refund_shipping_mismatch`).
- **Finding** — the structured output of one duty's deterministic SQL. Becomes a persisted `agent_findings` row after LLM narration + citation validation.
