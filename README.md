# Drishti

**AI ops analyst for D2C brands.** Cross-tool questions, cited answers, and a read-only agent that watches your stack.

> A v0 built against the Build brief: three connectors, a universal schema, a chat layer with a citation contract, and an autonomous agent. Submitted Sunday, 17 May 2026.

**Live demo**: [drishti-zeta.vercel.app](https://drishti-zeta.vercel.app) — sign in with any email or Google. Every signed-in account lands on the seeded **Merchant C** tenant (the [Auth / tenancy](#eval--where-it-breaks) section explains why; it's an intentional demo affordance, not a production tenancy model).

---

## What I built — 5-line architecture summary

1. FastAPI + Supabase Postgres (asyncpg, RLS-isolated) on the backend, Arq + Redis for sync / normalize / agent jobs, Next.js + Clerk on the web.
2. Three connectors (Shopify, Shiprocket, Razorpay) sit behind one interface — `Connector` / `ResourceSyncer` / `Transport` / `RateLimiter` — with swappable Live / Mock / Recording transports.
3. Every payload lands first in append-only `source_records`, then normalizers project it into typed domain tables (`orders`, `shipments`, `payments`, `refunds`, `settlements`, `order_links`) carrying five provenance fields on every row.
4. Chat uses eleven SQL tools — nine read-only plus two write tools that mutate finding lifecycle / duty configs — called from an OpenAI Responses-API tool loop; a deterministic citation validator rejects any answer that contains an uncited or mismatched number before it reaches the operator.
5. The RTO + Shipping-Margin agent runs four detection duties over the joined data, writes findings with structured proposed actions, and never executes anything against Shopify / Shiprocket / Razorpay.

### What's actually wired up

- 1 backend service (FastAPI, 61 pytest tests, ruff clean)
- 1 arq worker (15 job functions across sync / normalize / agent / cron)
- 17 alembic migrations covering 22 tables with RLS on all tenant-scoped tables
- 3 connector implementations, 9 syncer resources (Shopify orders/customers/products, Shiprocket shipments/tracking, Razorpay payments/refunds/settlements + 2 helpers)
- 1 agent with 4 duties
- 11 chat tools behind a typed `ToolResult` envelope (9 read-only + 2 write), called by OpenAI tool-use loop
- 3 webhook routes (Shopify HMAC verified; Shiprocket / Razorpay secret-verified)
- Next.js app with 5 routes (landing, dashboard, chat, findings, connections) + Clerk auth

> **What is *not* wired up:** the actual Shopify / Shiprocket / Razorpay HTTP APIs were never called against live merchant credentials in this build. The connector classes implement the documented auth + pagination shapes correctly; all sync runs in the demo use the **Mock transport** replaying JSON fixtures. See [Connectors — what's real vs what's mocked](#what-is-real-vs-what-is-mocked).

---

## Connectors — why these three

| Source | Why it earns a slot |
|---|---|
| **Shopify** | Commerce truth. Defines what an order is, what the customer paid, what the address is, whether the order is cancelled or refunded. Every downstream question starts here. |
| **Shiprocket** | Logistics truth. RTO state, courier, AWB, freight cost, pickup/delivery timestamps. Roughly half of D2C ops pain (returns, courier overcharges, delays) is *only* visible here. |
| **Razorpay** | Money truth. Captured vs failed payments, refund amount + timing, settlement reconciliation. Without it, "refund issued after shipment picked up" is unanswerable. |

The useful questions live in the *joins*. "Which COD lanes are losing money?" needs orders × shipments × payments. "Which refunds shipped before cancellation?" needs refunds × shipments × payments. One source on its own would tell you nothing you couldn't already see in its own dashboard.

The interface is intentionally boring:

```
connectors/base/
├── connector.py        # auth, refresh, request-with-retry, rate limit
├── resource_syncer.py  # paginated raw-page fetch into source_records
├── transport.py        # Live (httpx), Mock (fixture replay), Recording
├── rate_limiter.py     # token bucket per (merchant, source)
└── errors.py           # AuthError / RateLimitError / Transient / Permanent
```

Concrete syncers only own provider-specific auth, pagination, and the raw-payload write. Adding a fourth source means a new directory, an `authenticate()`, and one syncer per resource — no other code changes.

### What is real vs what is mocked

This is the single most important honesty point in the build:

| Component | Status |
|---|---|
| Connector abstraction (`Connector`, `ResourceSyncer`, `Transport`, `RateLimiter`) | **Real** — used by every demo path |
| `LiveTransport` (httpx-based) | **Coded, not exercised.** The class works; it has never been pointed at a real Shopify / Shiprocket / Razorpay endpoint with production credentials in this build. |
| `MockTransport` (fixture replay) | **Real and used everywhere in the demo** — every sync run, every normalize step, every agent run is driven by mock fixtures. |
| Shopify OAuth start + HMAC-verified callback | Coded against the documented Shopify OAuth flow; not exercised against a real Shopify store. |
| Shiprocket email/password login → bearer token | Coded against Shiprocket's documented `/v1/external/auth/login`; not exercised against a real Shiprocket account. |
| Razorpay key/secret save | Coded; not exercised against a real Razorpay account. |
| Shopify webhook HMAC verification | Coded correctly per Shopify docs; not replayed against signed payloads from a real store. |
| Shiprocket / Razorpay webhook secret verification | Coded; not replayed. |

**What this means in practice.** Pointing Drishti at a real merchant requires (a) putting real OAuth keys / credentials in `.env`, (b) flipping `DRISHTI_TRANSPORT=live` (or wiring the per-connection toggle), (c) almost certainly fixing a handful of pagination / rate-limit edge cases that only show up against real responses. The architecture is correct; the production integration work is not done.

---

## Schema — why this shape

Hybrid: append-only raw store + typed domain tables + provenance contract.

**`source_records`** stores the exact API payload Drishti fetched, immutably:

```
id, merchant_id, source, resource, source_record_id,
endpoint, payload (jsonb), payload_hash, fetched_at, sync_run_id
```

Trigger forbids `UPDATE`/`DELETE` on this table. Everything downstream can be replayed from it.

**Domain tables** (`orders`, `customers`, `products`, `order_line_items`, `shipments`, `tracking_events`, `payments`, `refunds`, `settlements`, `order_links`) carry the same five provenance fields on every row:

```
source            text   -- 'shopify' | 'shiprocket' | 'razorpay'
source_record_id  text   -- the source's primary key for the record
raw_record_id     uuid   -- → source_records(id)
sync_run_id       uuid   -- → sync_runs(id), nullable for webhook-derived rows
synced_at         timestamptz
```

A citation in a chat answer (`<cite row_id#field>value</cite>`) resolves through these fields back to the exact payload version that produced the number. There is no number in the UI that can't be traced.

**`order_links`** is the cross-source join key: `(order_id, shipment_id, payment_id, confidence)`. Built by a deterministic matcher in the normalize worker. Chat tools and agent duties filter on `confidence >= 0.8` so noisy weak matches don't pollute output.

**RLS.** Every tenant-owned table has `ENABLE ROW LEVEL SECURITY` + a `merchant_isolation` policy that reads `current_setting('app.current_merchant_id')`. The middleware sets that variable at the start of each request. A query that forgets `WHERE merchant_id = ...` can't leak across tenants.

Why two layers, not just normalized: raw keeps the system replayable and the citations honest (you can always show the actual payload Drishti read); normalized keeps tool queries fast and obvious. You get auditability and ergonomics at the cost of one extra write per record. Worth it.

---

## Chat — tool schema and citation contract

### The 9 read-only tools

All tools return the same envelope:

```
ToolResult {
  result_id: "tr_<hex12>"
  tool_name: str
  args: dict
  rows: CitedRow[]         # row_id, values, source, raw_record_id, fetched_from, synced_at
  aggregates: CitedAggregate[]   # agg_id, label, value, unit, derived_from_row_ids, formula
  metadata: dict
}
```

| Tool | What it returns |
|---|---|
| `query_orders` | Filterable order rows + count + total revenue aggregate |
| `query_shipments` | Filterable shipment rows + count |
| `query_payments` | Filterable payment rows + total paise aggregate |
| `rto_loss_by_pincode` | Pincode-grouped RTO freight loss + per-pincode aggregates + total |
| `courier_margin_by_route` | Route × courier freight totals + count |
| `delayed_prepaid_orders` | Prepaid shipments past expected delivery + count |
| `refund_shipping_mismatch_check` | Refunds processed after pickup + exposure aggregate |
| `list_findings` | Recent agent findings + count |
| `get_finding` | Single finding by id, with narrative + proposed action |

### The 2 write tools

These are the only chat surfaces that mutate state. The model is instructed to call them only when the operator explicitly asks for the mutation and supplies enough specifics to identify the row. Every call is persisted in `tool_calls` for audit.

| Tool | What it does | Required args |
|---|---|---|
| `update_finding_status` | Sets a finding's lifecycle (`open`, `acknowledged`, `actioned`, `dismissed`). Wraps `agent_findings.lifecycle_status`. | `finding_id`, `lifecycle_status` |
| `update_duty_config` | Enables or disables one of the four agent duties for the current merchant. Wraps `agent_duty_configs`. | `duty`, `enabled` |

Both return the post-mutation row as a single `CitedRow` so the model can reference the result in its answer. Rejected calls (unknown enum value, missing row) return an empty `rows` list with `metadata.status` set to `rejected` / `not_found`, never silently no-op.

**OpenAI is the default in this deployment.** With `OPENAI_API_KEY` set (which it is), every `POST /chat` runs through the OpenAI Responses API tool loop (`src/drishti/chat/loop.py:_openai_tool_draft`). The model sees all eleven functions, picks one or more, Drishti executes them server-side under the authenticated merchant, and feeds the typed `ToolResult` back as `function_call_output`. Up to 3 iterations per turn. The model also drafts agent finding narratives (`src/drishti/agents/rto_shipping_margin/narrator.py`).

### The citation contract

```
<cite ROW_ID#field>displayed_value</cite>
<cite AGG_ID>displayed_value</cite>
```

`src/drishti/chat/citation_validator.py` is deterministic regex + value comparison:

1. **Every numeric token in the answer must be inside a `<cite>` tag.** (Years like `2026` are whitelisted unless adjacent to a `₹` or `%`.)
2. **Every cite tag's id must resolve** to a row id or agg id in *this turn's* `tool_results`.
3. **The displayed value must equal the resolved value.** For `₹` displays, the displayed rupees ↔ paise math has to match. Mismatch → fail.

If validation fails after the OpenAI draft, a deterministic answer template runs over the same tool results and is re-validated. If even that fails, the offending `<cite>` blocks are redacted to `[uncited]` before the user sees them. No path lets an uncited number reach the response.

**Honest scope on the fallback path**: if `OPENAI_API_KEY` is unset (or every OpenAI retry fails for a request), chat falls back to keyword-based intent routing over the 9 read-only tools, then a deterministic answer template. The two write tools are intentionally unreachable on the fallback path — mutations require explicit operator intent, and keyword routing can't establish that. The citation contract is the same gate in both modes. This v0 deployment runs the OpenAI path; the fallback exists so the citation gate is the load-bearing component, not the model.

### Streaming

`POST /chat/stream` returns SSE events (`status`, `metadata`, `delta`, `done`). Today the answer is computed first and chunked into ~32-char `delta` events; it isn't true token streaming from the model. The frontend supports it cleanly — when we move to streamed model output, no UI work is needed.

---

## Agent — the RTO + Shipping-Margin Worker

**Trigger.** Two paths:
1. Manual run from the Findings page → enqueues an arq job → worker picks it up.
2. Cron at 03:00 IST → enqueues one job per merchant → each merchant gets a `hash(merchant_id) % 14400`-second random delay so 10k merchants don't all hit the DB at the same minute.

**Data.** Reads orders, shipments, payments, refunds, and `order_links` for the current merchant under RLS. Writes nothing outside of `agent_runs` and `agent_findings`. Never calls back to Shopify/Shiprocket/Razorpay.

**Four duties** (`src/drishti/agents/rto_shipping_margin/duties/`):

| Duty | What it detects | Proposed action |
|---|---|---|
| `cod_rto_risk` | COD pincode clusters with ≥40% RTO rate, ≥5 orders, ≥₹1k freight loss in 30 days | `require_prepaid_for_segment` |
| `courier_margin_drift` | Route × courier where freight-per-gram is ≥125% of the cheapest courier on that route, ≥5 shipments | `switch_default_courier_for_route` |
| `delayed_prepaid` | Prepaid, captured, ≥2 days past expected delivery, order ≥₹1k | `escalate_to_courier_support` |
| `refund_shipping_mismatch` | Refund processed *after* shipment pickup, not an RTO | `review_refund_policy_for_shipped_orders` |

Each duty: deterministic SQL detection → `Finding` dataclass → a tool-result-shaped record (so its numbers are themselves citable) → narrator (OpenAI when configured, deterministic template otherwise) → citation validation → insert.

**Why this agent.** Shipping margin is the largest recurring controllable cost for an Indian D2C brand. RTO + freight overcharges + missed refund exposure routinely run into single-digit percentages of revenue. It also forces real cross-tool reasoning across all three connectors, which is the whole point of the brief. A "send a Slack message when revenue dips" agent would have used only one source.

**Failure modes called out:**

- LLM narrative can fail the citation gate → falls back to a deterministic narrative; if *that* also fails, `narrative_status='degraded'` and the finding still surfaces with structured fields.
- A duty SQL error doesn't kill the run → captured per-duty in `errors`, run status becomes `partial`.
- Cancelled mid-run → checked between findings; partial findings already written are kept.
- Re-detections are deduped via `agent_findings.fingerprint` — a SHA-256 of `(duty, finding_type, sorted evidence_row_ids, action_type, parameters)`. Same problem on a new run hashes the same.

---

## Scale — 1 → 10,000 merchants

### What's already built

- Merchant-scoped schema with RLS on every tenant table.
- Indexes on `(merchant_id, …)` for every hot query path.
- Cursor-based syncers — restartable from where they left off, no full re-pulls.
- Append-only `source_records` so normalizers can be replayed without re-fetching external APIs.
- Token-bucket rate limiter keyed by `(merchant_id, source)`.
- Arq workers separate for sync, normalize, and agent — different queues can be scaled independently.
- Daily agent runs staggered over a 4-hour window so 10k merchants don't synchronise on the same minute.
- Connection pooling tuned tiny per app instance (`pool_size=5, max_overflow=10`); Supabase pgBouncer multiplexes upstream. asyncpg prepared-statement cache disabled so it survives transaction-mode pooling.
- Load harness (`scripts/load_harness.py`) — synthetic citation validator + agent SQL stress with concurrency.

### What breaks first at 10k

| Pressure point | Order of magnitude | Mitigation |
|---|---|---|
| `source_records` row count | 10k merchants × ~10k records ≈ **100M rows** | Hash partition by `merchant_id` before that point. Plumbing is ready — table is single-tenant-accessed only. |
| Repeated monthly aggregate queries (`query_orders` over 30 days) | Per-merchant ad-hoc, can spike DB CPU | Daily merchant-fact rollup tables (`daily_revenue`, `daily_freight`, `daily_refunds`). The chat tools would prefer rollups; the agent still needs the raw rows. |
| Connector API rate limits | Shopify ≈ 2 req/s, Shiprocket bursty, Razorpay 100/min | Already per-merchant rate-limited; next step is global token buckets per source to absorb shared-IP throttling. |
| Daily agent fan-out | 10k jobs × 0.5s each = ~1.4 wall-hours | Stagger window is already 4h. Real fix is multi-worker arq, sharded by `hash(merchant_id) % N`. |
| Webhooks burst | Black Friday-style spikes | Already deduped via `webhook_deliveries.external_id` unique index. Beyond ~500 RPS we'd front the webhook routes with a queue (SQS/Pubsub) and ack synchronously. |

### Honest harness numbers

`scripts/load_harness.py --merchants 100 --orders-per-merchant 500 --chat-turns 200 --agent-runs 100 --concurrency 25 --database-smoke` (latest run regenerated 2026-05-16, full report in `load_harness_report.md`):

- 200 synthetic chat citation turns, p95 **12.20 ms**, max 12.73 ms
- 100 synthetic agent scans, p95 **0.39 ms**, max 0.44 ms
- DB smoke count over 9 tables: **9.79 seconds** for the round trip — almost entirely network latency to the Supabase pooler in `ap-northeast-2`, not query time

Current row counts under the seeded demo (3 merchants):

| Table | Rows |
|---|---:|
| `source_records` | 12,836 |
| `orders` | 5,125 |
| `shipments` | 3,930 |
| `payments` | 3,772 |
| `agent_findings` | 229 |
| `agent_runs` | 31 |
| `chat_messages` | 68 |
| `tool_calls` | 86 |

The harness stresses the validator and the agent SQL shape *without* hitting third-party APIs. It is not a full multi-tenant soak. To call this "load tested at 10k" we'd need a staging DB seeded with 10k merchants and 10M+ orders, run for an hour.

---

## Eval — where it breaks

I'd rather call these out than have them found.

**Connectors (most important caveat)**
- **No real Shopify / Shiprocket / Razorpay API has been called against live merchant credentials in this build.** Every demo run uses `MockTransport` replaying fixtures. The `LiveTransport` (httpx) class is implemented but unexercised against real endpoints.
- Shopify OAuth start + HMAC callback are coded; not exercised against a real store.
- Shiprocket email/password login is coded against the documented endpoint; not exercised against a real account.
- Razorpay key/secret save is coded; not exercised against a real account.
- Webhook routes for all three sources exist with HMAC / secret verification + dedupe + normalize-enqueue; signed webhooks from real provider sandboxes have not been replayed.
- "Recording" transport works but there's no UI to flip a connector into record mode.

**Chat**
- The OpenAI tool loop caps at 3 tool-call iterations per turn. Deeper investigations get cut off.
- If OpenAI fails (rate limit, network), the fallback path is keyword-based intent routing over the 9 read-only tools — good enough to keep the citation contract intact, not a real LLM agent. The 2 write tools are deliberately unreachable on this path.
- The citation validator's regex tokenises numbers via a single `NUMBER_RE` — exotic formats (`1.23e6`, `1,23,000` Indian lakhs grouping) aren't on the whitelist and would either get auto-cited if they collide with a tool value, or get redacted otherwise.
- Streaming is response chunking, not model-token streaming. Visually the same; latency-wise it's the same as non-streaming.

**Agent**
- Findings dedupe by fingerprint exists, but the UI doesn't yet collapse "this is the 4th time we've seen this" into a history view.
- Proposed actions are stored as JSON and rendered as human-readable cards, but there's no integration to actually *execute* an action (intentional per the brief — calling out anyway).
- Narrator can degrade to `narrative_status='degraded'` when even the deterministic template fails citation; the UI handles it but the operator just sees an empty narrative field.

**Auth / tenancy**
- Clerk JWT template currently emits a hardcoded `merchant_id` for the demo. A production merchant flow would require a Clerk-org → merchant mapping table (table exists: `clerk_user_merchants`, just not wired into onboarding).
- The merchant switcher in the header is a demo affordance. A real signed-in user can't switch tenants.

**Scale**
- `source_records` is not yet partitioned. Below ~10M rows the cost is hypothetical.
- No aggregate rollup tables. Chat tools recompute from raw on every call.
- Load harness is synthetic + a DB smoke count; not a real 10k-merchant soak.
- The arq worker can hang for one job on a stale asyncpg connection past Supabase pgBouncer's idle window — the next pool checkout sits waiting on a server-side-recycled socket. arq's 300s job timeout catches it and the subsequent run uses a fresh connection. Setting `pool_recycle` shorter than pgBouncer's idle timeout would fix it cleanly; not done in this v0.

**Frontend**
- Chat history supports auto-save, click-to-load, delete, and timestamps. Rename, search, regenerate, and export are not built.
- Findings page supports lifecycle status changes and JSON export but doesn't expose run history (only the latest run's findings).
- The dashboard's "Ask Drishti" composer is a redirect to `/chat?q=…`. It doesn't run the query inline.

---

## Hours spent

Approximate: **45–55 hours across 7 distinct working days** (10–17 May 2026, with a 1-day gap around the 15th). The last working day added ~5 hours of live-deploy debugging that wasn't planned for.

Rough split:

| Bucket | Hours |
|---|---|
| Design docs, schema design, migration plan | 8 |
| Connector abstraction + 3 implementations + transports | 8 |
| Normalize workers + order_links matcher | 4 |
| Agent base + 4 duties + narrator + citation validation for findings | 7 |
| Chat tools + OpenAI tool-loop + citation validator | 7 |
| Frontend (landing, dashboard, chat, findings, connections, Clerk wiring) | 8 |
| Load harness, README, polish, live deploy on Vercel + Railway + Supabase + Upstash + Clerk (Nixpacks venv quirks, JWT lifecycle, CORS, idle-connection debugging) | 8 |

---

## What I'd do with another week

Ranked by impact:

1. **Partition `source_records` by `merchant_id` hash + add daily rollup tables.** The single biggest scale unlock. Schema change is straightforward; the migration is the work.
2. **Wire real OAuth onboarding** for all three connectors + a "Connect → first sync → first findings" guided flow. Today's connections page accepts credentials but the production onboarding loop isn't smooth.
3. **Replace the keyword router with a small open-weights model** as the fallback when no OPENAI_API_KEY. Keeps the citation contract; loses the keyword brittleness.
4. **True model-token streaming** for the chat loop. Frontend is already wired; backend needs to switch from `responses.create` to the streaming variant.
5. **Dedupe-aware findings UI.** Group findings by `fingerprint` so the operator sees "this RTO cluster has been flagged 5 times in 3 weeks" instead of 5 separate rows.
6. **Run the harness against a real 10k-merchant Supabase project**, not synthetic data. Publish the actual numbers, fix the first thing that breaks (almost certainly the unpartitioned `source_records` index).
7. **Add a fourth connector** — Meta Ads or Klaviyo would test the "swappable" claim with a different auth shape (Meta uses long-lived tokens; Klaviyo uses API keys with different rate-limit semantics).

---

## AI tools — what I wrote vs what the LLM wrote

Used Claude Code throughout. Honest breakdown:

| Mostly LLM-authored, edited by me | Mostly mine, LLM assisted |
|---|---|
| Frontend Tailwind + Next.js scaffolding | Schema design and migration ordering |
| Boilerplate routes, Pydantic models | Citation validator rules and edge cases |
| Test fixtures and lots of unit tests | Connector abstraction shape (transports, syncers) |
| Skeleton SQL queries for the chat tools | Agent duty SQL (the thresholds, the joins, the action shapes) |
| README structure | Decision on what to *not* build |

The architecture, the citation contract, the agent duty thresholds, and what counts as "honest scope" in this README were mine. Most of the typing was assisted.

---

## Architecture quick reference

```
src/drishti/
├── app.py                    # FastAPI factory, CORS, middleware order
├── worker.py                 # arq WorkerSettings, cron registration
├── queue.py                  # shared queue name
├── config.py                 # pydantic-settings; reads .env
├── observability.py          # Logfire setup
├── auth/                     # Clerk JWT verifier + tenant middleware
├── connectors/
│   ├── base/                 # Connector, ResourceSyncer, Transport, RateLimiter
│   ├── shopify/              # 3 syncers (orders, customers, products)
│   ├── shiprocket/           # 2 syncers (shipments, tracking)
│   └── razorpay/             # 3 syncers (payments, refunds, settlements)
├── webhooks/                 # HMAC / secret verifiers per source
├── workers/
│   ├── sync_worker.py        # 8 sync entrypoints
│   ├── normalize_worker.py   # raw → domain projections + order_links
│   └── agent_worker.py       # manual + scheduled + queued runs
├── agents/
│   ├── base/                 # Agent, Duty, Finding
│   └── rto_shipping_margin/  # 4 duties + narrator
├── chat/
│   ├── loop.py               # OpenAI tool loop + deterministic fallback
│   ├── citation_validator.py # the gate
│   └── tools/registry.py     # 11 tools (9 read + 2 write), typed envelope
├── routes/                   # health, chat, agents, findings, connections, webhooks, source_records, merchants, demo
└── db/
    ├── session.py            # asyncpg engine, RLS context helpers
    └── repositories/         # SQL by domain area

alembic/versions/             # 17 migrations
web/src/app/                  # Next.js App Router
scripts/                      # seed_demo, load_harness, seed_agent_demo
tests/                        # 61 pytest tests
```

---

## Run locally

```bash
cp .env.example .env
uv sync
cd web && corepack pnpm install && cd ..
make dev     # API + worker + web in parallel
```

Seed demo data (3 merchants) and run the agent once:

```bash
uv run python scripts/seed_demo.py --run-agent
```

Run the harness:

```bash
uv run python scripts/load_harness.py \
  --merchants 100 --orders-per-merchant 500 \
  --chat-turns 200 --agent-runs 100 \
  --concurrency 25 --database-smoke
```

Checks:

```bash
uv run pytest             # 61 tests
uv run ruff check .
cd web && corepack pnpm lint
```

---

## Deployment

The live v0 runs across five free-tier services:

| Service | Region | What it hosts |
|---|---|---|
| **Vercel** | Global edge | Next.js frontend (`web/`) at `drishti-zeta.vercel.app` |
| **Railway** | `europe-west4` | FastAPI API (`drishti.app:create_app`) + arq worker (`drishti.worker.WorkerSettings`) — two services, same repo |
| **Supabase** | `ap-northeast-1` (Tokyo) | Postgres via the transaction pooler (asyncpg, prepared-statement cache disabled) — all 17 migrations applied |
| **Upstash** | `ap-northeast-1` (Tokyo) | Redis with TLS (`rediss://`) — arq job queue |
| **Clerk** | Global | Auth, JWT issuance with a `drishti` template that emits a hardcoded `merchant_id` claim. Dev mode for this demo. |
| **OpenAI** | — | `gpt-5.2` for chat tool-loop + agent narrator |

Total cost so far: $0. Estimated steady-state at single-merchant demo traffic: ~$5–10/month, mostly OpenAI.

**API start command** (Railway):

```
if [ -x /app/.venv/bin/alembic ]; then VENV=/app/.venv; else VENV=/opt/venv; fi && \
  $VENV/bin/alembic upgrade head && \
  exec $VENV/bin/uvicorn drishti.app:create_app --factory --host 0.0.0.0 --port $PORT
```

**Worker start command** (Railway):

```
if [ -x /app/.venv/bin/arq ]; then exec /app/.venv/bin/arq drishti.worker.WorkerSettings;
  else exec /opt/venv/bin/arq drishti.worker.WorkerSettings; fi
```

The conditional venv path is bulletproof against Nixpacks' Python provider occasionally choosing `/opt/venv` over `/app/.venv` for the synced environment.

**CORS** is gated by `DRISHTI_WEB_ORIGIN` on the API. Set it to the canonical Vercel domain — preview deployment URLs are intentionally outside the allowlist.

**Auth flow on the live demo**: Clerk issues a JWT with the `drishti` template, which carries `merchant_id` and `aud: drishti-api` as literal claims. The API's `ClerkJWTVerifier` validates `iss` against the Clerk Frontend API URL, `aud` against `CLERK_JWT_AUDIENCE`, signature via JWKS, and extracts `merchant_id` directly from claims for any authenticated user. There is no per-user `clerk_user_merchants` mapping for the demo (the table exists but isn't required on this path).
