# Drishti - AI ops analyst for D2C brands

Drishti is a working v0 of an AI employee for Indian D2C operators. It connects commerce, logistics, and payments data into one merchant-scoped workspace; normalizes every source row with provenance; answers cross-tool questions with cited numbers; and runs a read-only RTO + shipping-margin agent that proposes money-saving actions without executing them externally.

## Five-line architecture

FastAPI is the API layer, Supabase Postgres is the system of record, and Arq/Redis runs sync, normalize, and agent jobs. Shopify, Shiprocket, and Razorpay share one connector abstraction with swappable live/mock transports. Every API payload lands first in append-only `source_records`, then normalizers project it into typed domain tables with `raw_record_id` provenance. Chat uses read-only tools that return typed rows and aggregates; the citation validator blocks uncited or mismatched numerical claims. The Next.js app exposes a demo dashboard, cited chat, raw evidence drill-down, and the agent run log.

## What I built

- FastAPI backend with health, Clerk/demo auth, merchant-scoped middleware, cited chat, findings, source-record, agent, and Shopify webhook routes.
- Supabase/Postgres schema through Alembic migrations for merchants, connections, raw source records, normalized commerce/logistics/money tables, chat logs, tool calls, webhook deliveries, agent runs, and findings.
- Three connector implementations behind one interface: Shopify, Shiprocket, Razorpay.
- Two-stage ingestion: sync writes raw source records, normalize workers project into domain tables, and order links join Shopify orders to Shiprocket shipments and Razorpay payments.
- Cited chat UI: answers include `<cite>` markers, evidence rows, and raw source-record drill-down.
- RTO + Shipping Margin Worker: four duties, one run log, cited narratives, and structured proposed actions.
- Demo seed for three merchants and a scale harness report in `load_harness_report.md`.

Relevant paths:

- Backend app: `src/drishti/app.py`
- Connector base: `src/drishti/connectors/base/`
- Connectors: `src/drishti/connectors/shopify/`, `src/drishti/connectors/shiprocket/`, `src/drishti/connectors/razorpay/`
- Chat tools and validator: `src/drishti/chat/tools/registry.py`, `src/drishti/chat/citation_validator.py`, `src/drishti/chat/loop.py`
- Agent: `src/drishti/agents/rto_shipping_margin/`
- Frontend: `web/src/app/`
- Load harness: `scripts/load_harness.py`

## Auth

The Next.js app uses Clerk App Router auth:

- `web/src/proxy.ts` runs `clerkMiddleware()` and protects `/dashboard`, `/chat`, and `/findings`.
- `web/src/app/layout.tsx` wraps the app in `ClerkProvider`.
- Navigation uses Clerk `Show`, `SignInButton`, `SignUpButton`, and `UserButton`.
- Browser API calls use `useAuth().getToken()` when a user is signed in.
- Local demo tokens remain as a fallback for seeded local demos.

The FastAPI backend verifies bearer JWTs and extracts `merchant_id` for tenant scope and Postgres RLS. For the live demo, the Clerk JWT template `drishiti` emits:

```json
{
  "aud": "drishti-api",
  "merchant_id": "00000000-0000-0000-0000-00000000000c"
}
```

That static merchant UUID is deliberate for this v0 hosted/demo flow. It proves Clerk login plus backend JWT verification without adding a full onboarding/organization-to-merchant mapping workflow.

The merchant selector in the header is also demo-only. It exists so reviewers can compare seeded Merchant A/B/C data quickly. In a production merchant login flow, a signed-in merchant should land in their own workspace and should not be able to freely switch tenants. Merchant switching should only be available to internal admins, demo reviewers, or users who belong to multiple Clerk Organizations with an explicit org-to-merchant mapping.

## Connectors

The three connectors are:

- **Shopify**: commerce truth for orders, customers, products, payment method, order value, and customer destination.
- **Shiprocket**: logistics truth for shipments, couriers, freight cost, tracking state, delivery/RTO signals.
- **Razorpay**: money truth for payments, refunds, fees, and settlement context.

These three were chosen because the useful operational questions live in the joins. A Shopify order has a Shiprocket shipment and a Razorpay payment/refund. No single SaaS dashboard answers “which COD lanes are losing money?” or “which refunds shipped before cancellation?” The connector design is intentionally boring: `Connector`, `ResourceSyncer`, `Transport`, and `RateLimiter` are shared; concrete syncers only own provider-specific auth, pagination, and normalization.

Current demo mode uses fixtures/seeded data through the same schema and tool paths. The transport abstraction supports live HTTP, mock replay, and recording. Shopify webhook validation is implemented; Shiprocket/Razorpay live webhook handling is documented as v1.

More detail: `docs/CONNECTORS.md`.

## Schema

The schema is hybrid:

- `source_records` stores immutable raw API responses, with source, resource, endpoint, fetched timestamp, payload hash, and merchant scope.
- Domain tables (`orders`, `shipments`, `payments`, `refunds`, `settlements`, etc.) store normalized operational fields.
- Every domain row carries provenance: `source`, `source_record_id`, `raw_record_id`, `sync_run_id`, `synced_at`.
- `order_links` resolves cross-source joins so chat and agents can reason across commerce, logistics, and money.
- RLS policies scope tenant-owned tables by `current_setting('app.current_merchant_id')`.

Why this shape: raw records keep auditability and replayability; domain tables keep tool queries fast and understandable; provenance fields make citations resolve back to the exact API payload version.

More detail: `docs/SCHEMA.md`.

## Chat

The chat layer exposes read-only tools that return a common `ToolResult` shape:

- `rows`: cited domain or derived rows with row IDs and provenance.
- `aggregates`: cited values with formula and derived row IDs.
- `metadata`: limit, freshness, and filter context.

Tools implemented:

- `query_orders`
- `query_shipments`
- `query_payments`
- `rto_loss_by_pincode`
- `courier_margin_by_route`
- `delayed_prepaid_orders`
- `refund_shipping_mismatch_check`
- `list_findings`
- `get_finding`

When `OPENAI_API_KEY` is configured on the backend, chat uses the OpenAI Responses API with function tools mapped to Drishti's `TOOL_REGISTRY`. The model chooses which read-only tools to call, Drishti executes them server-side under the authenticated merchant context, feeds tool results back to the model, then validates the final answer before returning it to the user.

The citation validator is deterministic. It parses every `<cite id>number</cite>` claim, checks the cited ID exists in the current turn's tool results, checks the displayed number matches the tool value, and rejects uncited numbers. If OpenAI returns an invalid or uncited answer, Drishti falls back to a deterministic cited answer over the same tool results; if validation still fails, uncited values are redacted.

Important eval honesty: live tool selection depends on `OPENAI_API_KEY`. Without it, Drishti uses deterministic intent routing over the same tool registry. The citation contract is the final gate in both modes.

More detail: `docs/CITATION_CONTRACT.md`.

## Agent

The AI employee is the **RTO + Shipping Margin Worker**. It runs manually from the UI/API and on a scheduled worker cron. It is read-only by construction: it writes findings and proposed actions to Drishti, but never mutates Shopify, Shiprocket, Razorpay, or customer-facing state.

Duties:

- `cod_rto_risk`: finds COD pincode clusters with high RTO freight loss.
- `courier_margin_drift`: finds courier/route groups with freight premium against alternatives.
- `delayed_prepaid`: flags prepaid shipments past expected delivery.
- `refund_shipping_mismatch`: finds refunds issued after shipment pickup.

Each duty follows the same pattern: deterministic SQL detection, structured finding, cited narration, proposed action. Proposed actions are stored as JSON for machine-readability and rendered in the UI as operator-facing actions.

Why this agent: shipping margin is a large, recurring cost center for Indian D2C brands, and it forces real cross-source reasoning across orders, shipments, payments, and refunds.

More detail: `docs/AGENT.md`.

## Scale

What is already built:

- Merchant-scoped schema and RLS policies.
- Every tenant table indexed around `merchant_id`.
- Cursor-based resource syncers.
- Arq worker separation for sync, normalize, and agent jobs.
- Token-bucket rate limiter abstraction for connector requests.
- Per-merchant scheduled agent staggering over a four-hour window.
- Append-only raw store so normalizers can be replayed without refetching external APIs.
- Load harness: `scripts/load_harness.py`.

Harness run included in this repo:

- Report: `load_harness_report.md`
- Scenario: 100 merchants, 500 orders/merchant, 200 chat turns, 100 agent scans, concurrency 25.
- Synthetic chat citation p95: see report.
- Synthetic agent scan p95: see report.
- Database smoke count query also ran against the configured Supabase Postgres database.

What breaks first at 10k merchants:

- `source_records` volume grows fastest. At 10k merchants x 10k source records, it reaches 100M rows. The v1 plan is hash partitioning by `merchant_id`.
- Repeated month-level chat aggregates will need rollup tables or materialized daily merchant facts.
- Connector limits become the operational bottleneck before CPU. Queue partitioning by `(source, priority)` and per-source rate limits are the mitigation path.
- Agent runs must remain scheduled/staggered; running all merchants at 03:00 would spike DB and Redis.

## Local development

```bash
cp .env.example .env
cp web/.env.example web/.env.local
uv sync
cd web && corepack pnpm install
```

For Clerk-backed browser API calls, set these in `web/.env.local`:

```bash
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_...
CLERK_SECRET_KEY=sk_...
CLERK_JWT_ISSUER=https://...
CLERK_JWT_AUDIENCE=drishti-api
NEXT_PUBLIC_CLERK_JWT_TEMPLATE=drishiti
```

Run everything locally:

```bash
make dev
```

If port 3000 is occupied, Next.js may choose 3001. Local CORS allows both.

Seed demo data and run the agent:

```bash
uv run python scripts/seed_demo.py --run-agent
```

Run the harness:

```bash
uv run python scripts/load_harness.py --merchants 100 --orders-per-merchant 500 --chat-turns 200 --agent-runs 100 --concurrency 25 --database-smoke
```

Run checks:

```bash
uv run pytest
uv run ruff check .
cd web && corepack pnpm lint
```

## Deployment notes

The intended topology:

- API: Railway service running `uv run uvicorn drishti.app:create_app --factory --host 0.0.0.0 --port $PORT`
- Worker: Railway service running `uv run arq drishti.worker.WorkerSettings`
- Redis: Railway Redis
- Web: Vercel or Railway Next.js service pointing `NEXT_PUBLIC_API_URL` at the API
- Database: Supabase Postgres via `DATABASE_URL`
- Observability: Logfire via `LOGFIRE_TOKEN`

Production env must set:

- `DATABASE_URL`
- `REDIS_URL`
- `DRISHTI_ENV=production`
- `DRISHTI_WEB_ORIGIN`
- `DRISHTI_EXTRA_CORS_ORIGINS` for preview URLs if needed
- `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`
- `CLERK_SECRET_KEY`
- `CLERK_JWT_ISSUER`
- `CLERK_JWT_AUDIENCE=drishti-api`
- Clerk JWT template name on the web service via `NEXT_PUBLIC_CLERK_JWT_TEMPLATE`
- `OPENAI_API_KEY` for live chat tool-calling and agent narration
- `LOGFIRE_TOKEN` for traces

## Where it breaks

- Live OAuth is not fully productized for all three connectors. The connector implementations and transport boundary exist; demo data uses fixtures/seeds.
- OpenAI tool-calling is enabled only when the backend `OPENAI_API_KEY` is configured; otherwise chat falls back to deterministic routing.
- Clerk sign-in/sign-up and protected routes are implemented. Full Clerk Organization switching is not wired yet; the demo JWT template maps signed-in users to Merchant C through a static merchant UUID claim, while the visible merchant selector remains a demo affordance rather than production tenant-switching behavior.
- Supabase is used as direct Postgres through SQLAlchemy/asyncpg, not via `supabase-js`, so Supabase API request metrics may show zero.
- Historical agent runs are stored, but the Findings UI intentionally starts empty and populates only after a page-level run to make the demo flow clear.
- No partitioning yet on `source_records`.
- No hot aggregate rollups yet.
- Load harness is synthetic plus DB smoke, not a full multi-tenant soak test against external APIs.

## Hours spent

Approximate build time: 35-45 hours across five sessions.

Major buckets:

- Design docs and schema: 7-9 hours
- Connector abstraction and sync/normalize path: 7-8 hours
- Citation contract and chat tools: 6-7 hours
- Agent duties and run log: 6-7 hours
- Frontend and demo seed: 5-6 hours
- Harness, README, and polish: 4-5 hours

## What I would do with another week

- Add streaming UI for OpenAI tool calls and partial answers while keeping the same validator.
- Finish real OAuth/setup screens for Shopify, Shiprocket, and Razorpay.
- Add rollup tables for daily revenue, freight, RTO, and refund exposure.
- Partition `source_records`.
- Add a real load run at 1k merchants on a staging database.
- Expand citation UI to show aggregate formulas and derived row chains more cleanly.
- Add Clerk Organization switching and persist a Clerk-org-to-merchant mapping.
- Add route-level Logfire screenshots to the README.

## AI tools

I used AI coding assistance heavily. The architecture, schema, agent framing, and citation contract were designed through iterative prompts and review. Boilerplate, route scaffolding, Next.js UI, and some tests were AI-assisted and then edited. The SQL duty logic, citation validator behavior, RLS/security stance, and final eval-honesty sections were reviewed manually because those are load-bearing for correctness.
