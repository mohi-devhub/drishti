# Drishti — Connectors

This document covers the connector layer: the abstraction every connector implements, the three concrete connectors (Shopify, Shiprocket, Razorpay), the `Transport` protocol that swaps live HTTP for replayed fixtures, and the fixture system. Schema details for what connectors write live in `SCHEMA.md`.

The brief asks for *"one interface, three real implementations, swappable."* This document is the proof of that line.

## 1. The shape

```
connectors/
  base/
    connector.py          # abstract Connector
    resource_syncer.py    # abstract ResourceSyncer
    transport.py          # Transport protocol + Live, Mock, Recording impls
    rate_limiter.py       # Redis-backed token bucket
    cursors.py            # Cursor abstraction
    errors.py             # Connector exceptions taxonomy
  shopify/
    connector.py          # ShopifyConnector
    syncers/
      orders.py
      customers.py
      products.py
    webhooks.py           # HMAC validation + topic dispatch
    fixtures/             # captured + sanitized JSONs
  shiprocket/
    connector.py          # ShiprocketConnector
    syncers/
      shipments.py
      tracking.py
    fixtures/
  razorpay/
    connector.py          # RazorpayConnector
    syncers/
      payments.py
      refunds.py
      settlements.py
    fixtures/
```

The evaluator opening this tree should immediately see: three connectors, each declaring exactly the resources it actually has, all sharing the same base. That's what "one interface, three real implementations, swappable" looks like at the file-tree level.

## 2. The base abstractions

### 2.1 `Connector`

Owns auth, transport, rate limiting, retry, and acts as the parent of resource syncers.

```python
class Connector(ABC):
    source: ClassVar[str]                  # 'shopify' | 'shiprocket' | 'razorpay'
    base_url: ClassVar[str]
    rate_limit_config: ClassVar[RateLimitConfig]

    def __init__(
        self,
        connection: Connection,
        transport: Transport,
        rate_limiter: RateLimiter,
    ): ...

    @abstractmethod
    async def authenticate(self) -> AuthHeaders: ...

    @abstractmethod
    async def refresh_credentials_if_needed(self) -> None: ...

    @abstractmethod
    def syncer(self, resource: str) -> ResourceSyncer:
        """Returns the appropriate ResourceSyncer for a resource type.
        Raises UnsupportedResource if this connector doesn't have it."""

    async def request(self, method: str, path: str, **kwargs) -> Response:
        """Common HTTP path: auth headers + rate limiting + retry +
        instrumentation. Always goes through self.transport."""
```

Three rules every concrete connector follows:

1. **It declares only the resources it has.** `ShiprocketConnector.syncer('payments')` raises `UnsupportedResource`. The `syncer()` method is a typed registry; there is no fake `sync_payments()` returning empty.
2. **It never opens its own HTTP client.** All requests go through `self.transport`, which means swapping live for fixtures is one constructor argument.
3. **It never normalizes data into domain shapes.** That's the syncer's job, in stage 2.

### 2.2 `ResourceSyncer`

One per (connector, resource_type). Four methods:

```python
class ResourceSyncer(ABC):
    connector: Connector
    resource: ClassVar[str]                # 'orders', 'shipments', 'payments', ...

    @abstractmethod
    async def fetch_page(self, cursor: Cursor | None) -> Page:
        """Fetches the next page from the source.
        Page = (records: list[RawRecord], next_cursor: Cursor | None, has_more: bool)"""

    @abstractmethod
    def cursor_from(self, page: Page) -> Cursor | None: ...

    @abstractmethod
    def normalize(self, raw: RawRecord) -> NormalizedRecord:
        """Pure function. Takes a raw payload, returns a typed domain row dict.
        Called by the normalize_worker, not the sync_worker."""

    async def upsert(self, normalized: NormalizedRecord, raw_record_id: UUID, sync_run_id: UUID) -> None:
        """Default impl: INSERT ... ON CONFLICT (merchant_id, source, source_record_id) DO UPDATE.
        Concrete syncers override for cross-source linkage logic (see order_links)."""
```

The orchestrator (in the sync_worker) calls `fetch_page` + `cursor_from` in a loop until `has_more` is False, writing every record to `source_records` and enqueuing a normalize job per record. The normalize_worker calls `normalize` + `upsert` later, asynchronously.

### 2.3 `Transport` protocol

The piece that makes mock/live swappable.

```python
class Transport(Protocol):
    async def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        params: dict | None = None,
        json: dict | None = None,
        timeout: float = 30.0,
    ) -> Response: ...
```

Three implementations:

- **`LiveTransport`** — wraps `httpx.AsyncClient`. Used in production and when the env var `DRISHTI_TRANSPORT=live` is set per-connector.
- **`MockTransport`** — looks up a fixture by `(method, url_pattern, query_signature)` from the connector's `fixtures/` directory and returns it. Default in dev and demo.
- **`RecordingTransport`** — wraps `LiveTransport`, additionally writes every response to `fixtures/` after sanitizing PII. Used once during fixture capture; never enabled in deployment.

Selection happens at the application boundary:

```python
def build_connector(connection: Connection) -> Connector:
    transport_mode = settings.transport_mode_for(connection.source)  # 'live' | 'mock'
    transport = LiveTransport() if transport_mode == 'live' else MockTransport(source=connection.source)
    rate_limiter = RateLimiter.for_source(connection.source)
    return CONNECTOR_REGISTRY[connection.source](connection, transport, rate_limiter)
```

The connector doesn't know which transport it has and doesn't care.

### 2.4 `RateLimiter`

Token-bucket, Redis-backed for cross-worker coordination. One bucket per (merchant_id, source) tuple in v0; per (merchant_id, source, endpoint) is the natural scale-up path documented in `PRD.md`.

```python
class RateLimitConfig:
    requests_per_second: float
    burst: int
```

Per-source defaults from each provider's published limits (see §3, §4, §5). Mock transport has the rate limiter disabled — fixtures are infinite.

### 2.5 `Cursor`

Cursors are connector-specific JSONB blobs persisted on `connections.cursors`. Examples:

- Shopify orders: `{"updated_at_min": "2026-05-09T22:00:00Z", "page_info": null}`
- Shiprocket shipments: `{"from_date": "2026-05-09", "page": 12}`
- Razorpay payments: `{"from": 1715212800, "to": 1715299200, "skip": 0}`

The base `Cursor` type is `dict[str, Any]`; each syncer's `cursor_from(page)` returns the next state, and `fetch_page(cursor)` consumes it. The orchestrator never inspects cursors.

### 2.6 Connector errors taxonomy

```
ConnectorError
├── AuthError               # 401, expired token, refresh failed
├── RateLimitError          # 429; carries Retry-After
├── TransientError          # 5xx, timeouts, connection resets
├── PermanentError          # 4xx (non-401, non-429), bad request shape
└── UnsupportedResource     # Caller asked for a resource this connector doesn't have
```

The orchestrator retries `TransientError` with exponential backoff (max 3) and `RateLimitError` honoring `Retry-After`. `AuthError` triggers a refresh attempt then surfaces. `PermanentError` and `UnsupportedResource` fail the sync run with `status='failed'`, no retry.

## 3. Shopify connector

### 3.1 Why we picked Shopify (and not WooCommerce)

WooCommerce has more Indian D2C footprint by merchant count, but Shopify has cleaner OAuth, predictable response shapes, mature webhooks with HMAC validation, and free dev stores that let us prove a real live OAuth path for evaluation. WooCommerce's REST API depends on each merchant's WordPress version + plugin set, which is a fixture nightmare. The brief asks "why these three" — for Shopify specifically, the answer is *fixture predictability and a real live demo path*, not market share.

### 3.2 Auth

OAuth 2.0. We register Drishti as a Shopify Partners app; merchants install via standard install flow. Access tokens are long-lived (no refresh dance). Stored in `connections.auth_payload` as `{"access_token": "...", "shop": "merchant-name.myshopify.com", "scopes": [...]}`.

### 3.3 Rate limit

Shopify REST: ~2 requests/second per shop on standard plan, 4/sec on Shopify Plus, with a leaky bucket of 40. Drishti uses a conservative 2 req/sec/shop with burst=10. Higher-tier merchants would override this from `connections.auth_payload.rate_limit_override` (deferred; v0 hardcodes).

### 3.4 Resources synced

| Resource | Endpoint | Cursor strategy |
|---|---|---|
| `orders` | `GET /admin/api/2026-01/orders.json?status=any&updated_at_min=...` | `updated_at_min` + Shopify's `Link` header `page_info` cursor |
| `customers` | `GET /admin/api/2026-01/customers.json?updated_at_min=...` | Same shape |
| `products` | `GET /admin/api/2026-01/products.json?updated_at_min=...` | Same shape |

Shopify's REST Admin API is legacy. Drishti uses it only as a v0 demo shortcut for a controlled dev-store/custom-app path; production should use the GraphQL Admin API. We do not sync inventory, locations, fulfillments-as-separate-resource, or refund line items in v0. Refunds are part of the order payload and we promote what we need from `extras`. Documented gap: `fulfillments` would matter if we wanted to track partial shipment timing more precisely; deferred.

### 3.5 Webhooks (the only fully-wired webhook path in v0)

Endpoint: `POST /webhooks/shopify/{topic}`.

Topics handled:
- `orders/create`, `orders/updated`, `orders/cancelled`
- `customers/create`, `customers/update`
- `products/create`, `products/update`
- `app/uninstalled` (revokes connection)

Flow on each delivery:

1. Validate `X-Shopify-Hmac-Sha256` header against the request body using the app secret. Reject 401 on mismatch.
2. `INSERT INTO webhook_deliveries (merchant_id, source='shopify', external_id=X-Shopify-Webhook-Id, ...) ON CONFLICT DO NOTHING`. Duplicates are immediate 200 OK no-ops.
3. Write the body to `source_records` (raw JSONB).
4. Enqueue a `normalize_shopify_<resource>(raw_record_id)` job.
5. Return 200 within the 5-second Shopify timeout. The actual normalize happens asynchronously.

This converges with the polling sync path: webhooks and polls produce the same `normalize_*` jobs against the same `source_records` rows.

### 3.6 Fixtures

`connectors/shopify/fixtures/`:

```
orders_page_1.json          # first page of orders for merchant_b
orders_page_2.json
orders_page_3.json
customers.json
products.json
webhook_orders_create.json  # one example webhook body, signed
webhook_orders_updated.json
```

Captured from a Shopify dev store seeded with synthetic Indian addresses (Bangalore/Mumbai/Delhi pincodes), realistic SKUs, mixed COD/prepaid orders. Sanitized: real merchant info replaced with the Drishti dev store's; PII regenerated via Faker.

## 4. Shiprocket connector

### 4.1 Why Shiprocket

Shiprocket is the dominant aggregator for Indian D2C shipping. The single-API surface across multiple couriers (Delhivery, Bluedart, Ekart, Xpressbees) is *exactly* the abstraction founders need but don't have time to build. Without Shiprocket data, the agent cannot reason about courier efficiency or RTO patterns — which is the entire point of the worker. Picking Shiprocket over a single courier API is a judgment call about *what's relevant to Indian D2C*.

### 4.2 Auth

Email/password → token. Tokens last ~10 days. Stored as `{"token": "...", "issued_at": "...", "expires_at": "..."}`. `refresh_credentials_if_needed` re-authenticates with stored email/password when `expires_at - now < 24h`.

The credential storage is the most sensitive in v0 — Shiprocket's auth model is simpler than OAuth but means we hold the merchant's password. This must be protected with app-level envelope encryption or Supabase Vault, not only database encryption at rest. The README's eval-honesty section calls this out and notes that production would gate Shiprocket connections behind a hardware-backed secret store.

### 4.3 Rate limit

Shiprocket's documented limit is 100 requests/minute per token. Drishti uses 50/min with burst=5 (conservative; throttles before they do, never seeing a 429 in practice). The lower number leaves headroom for webhook-driven catch-up syncs.

### 4.4 Resources synced

| Resource | Endpoint | Cursor strategy |
|---|---|---|
| `shipments` | `GET /v1/external/shipments?from=YYYY-MM-DD&page=N` | `(from_date, page)`; `from_date` advances when prior page count exhausts |
| `tracking` | `GET /v1/external/courier/track/awb/{awb}` | Per-shipment, fan-out from `shipments` |

Tracking is fan-out: after fetching shipments, we enqueue a `sync_shiprocket_tracking(shipment_awb)` job per active shipment. Tracking events are append-only into `tracking_events`.

We do not sync orders (they originate in Shopify and are linked by Shiprocket's internal `order_id` field), couriers list (looked up on demand), serviceability (deferred — would matter for the courier-margin duty's "would another courier deliver here?" extension).

### 4.5 Webhooks (sketched, not built in v0)

Shiprocket supports webhooks for shipment status changes, but the sandbox doesn't reliably fire them. The webhook endpoint exists at `POST /webhooks/shiprocket/status` and validates the (weak) shared-secret header, but no production wiring is done. The endpoint logs the body and returns 200; nothing is normalized from it.

The README will be explicit: Shopify proves the webhook pattern; Shiprocket and Razorpay would follow the same shape (HMAC/secret validation + idempotency table + normalize-job enqueue), and the code structure is in place.

### 4.6 Fixtures

`connectors/shiprocket/fixtures/`:

```
shipments_page_1.json       # mixed delivered, in_transit, RTO statuses
shipments_page_2.json       # specifically seeded RTO cluster for pincode 110XXX
tracking_AWB123456789.json  # multi-event timeline ending in delivered
tracking_AWB987654321.json  # multi-event timeline ending in RTO
tracking_AWB555555555.json  # stuck-in-transit (delayed-prepaid duty test)
```

Captured from Shiprocket's sandbox plus a few hand-edited fixtures for the RTO cluster scenario (sandbox doesn't naturally generate clean clusters).

## 5. Razorpay connector

### 5.1 Why Razorpay

Razorpay is the default payment gateway for Indian D2C. UPI, cards, wallets, COD reconciliation, settlements — all under one API. Without Razorpay data, "is this order's payment captured?" and "did this refund go out?" can't be answered with confidence. PayU, Cashfree, and Stripe-India are alternatives, but Razorpay's API is the most documented and has the widest D2C adoption.

### 5.2 Auth

Basic auth with API key + secret. Two key pairs per merchant (test mode and live mode). v0 fixtures use a captured test-mode response set; live OAuth is not in v0 (Razorpay's onboarding flow for connected accounts is heavier than the budget allows).

Stored as `{"key_id": "rzp_test_...", "key_secret": "<encrypted>", "mode": "test"}`. The connector adds `Authorization: Basic base64(key_id:key_secret)` on every request.

### 5.3 Rate limit

Razorpay's API limit is 1000/min on standard accounts (high). Drishti uses 60/min with burst=10 — well below ceiling, so this is not a bottleneck even at scale.

### 5.4 Resources synced

| Resource | Endpoint | Cursor strategy |
|---|---|---|
| `payments` | `GET /v1/payments?from=<unix>&to=<unix>&skip=N&count=100` | `(from, to, skip)` window |
| `refunds` | `GET /v1/refunds?from=<unix>&to=<unix>&skip=N&count=100` | Same shape |
| `settlements` | `GET /v1/settlements?from=<unix>&to=<unix>&skip=N&count=100` | Same shape |

Razorpay paginates by `skip + count` rather than cursor; we use `from`/`to` to bound windows and `skip` to walk within. The `cursor_from` advances `skip` until the page is empty, then advances the window forward by 7 days.

### 5.5 Webhooks (sketched)

Razorpay's webhook system is mature and HMAC-validated. The endpoint `POST /webhooks/razorpay/{event}` exists and validates `X-Razorpay-Signature`; in v0 it logs and returns 200 without enqueuing normalize jobs. Same pattern as Shiprocket: the shape is in place.

### 5.6 Fixtures

`connectors/razorpay/fixtures/`:

```
payments.json               # mix of captured, failed, refunded
refunds.json                # several aligned to payments above
settlements.json            # daily payouts with realistic fee/tax breakdowns
```

Test-mode captures with merchant-identifying fields neutralized.

## 6. Adding a fourth connector — the proof of swappability

Hypothetical: the merchant wants to add **Delhivery** as a direct courier connector (bypassing Shiprocket). The work:

1. **Create `connectors/delhivery/connector.py`** — inherits `Connector`, sets `source='delhivery'`, fills in `authenticate` and `refresh_credentials_if_needed`.
2. **Create `connectors/delhivery/syncers/shipments.py`** — inherits `ResourceSyncer`, implements `fetch_page`, `cursor_from`, `normalize`. Normalization emits the same `shipments` schema as Shiprocket's syncer.
3. **Add to `CONNECTOR_REGISTRY`** in `connectors/registry.py`.
4. **Capture fixtures** with `RecordingTransport` against Delhivery's sandbox.
5. **Add OAuth callback** to `/connections/delhivery/callback`.
6. **Done.** No changes to: chat tools, agent duties, schema, RLS, citation contract, frontend chat UI. The agent's queries on `shipments` see Delhivery shipments alongside Shiprocket shipments transparently — `source` is just another column.

The README will reference this section under "what you'd do with another week" if we want to demonstrate breadth, or as the response to "why is this swappable?".

## 7. The fixture system

### 7.1 Structure

```
connectors/{source}/fixtures/
  index.yaml                  # method+url+params -> filename mapping
  *.json                      # the fixture bodies
```

`index.yaml` is the routing table for `MockTransport`:

```yaml
- match: { method: GET, path: /admin/api/2026-01/orders.json, params: { page_info: null } }
  file: orders_page_1.json
  status: 200
  headers:
    Link: '</admin/api/2026-01/orders.json?page_info=eyJsYXN0X2lkIjo1MDAxfQ>; rel="next"'
- match: { method: GET, path: /admin/api/2026-01/orders.json, params: { page_info: "eyJsYXN0X2lkIjo1MDAxfQ" } }
  file: orders_page_2.json
  status: 200
```

Match precedence: literal value > regex > absent (any). The MockTransport raises `FixtureNotFound` if no rule matches, which surfaces as a test failure.

### 7.2 Recording fixtures

```bash
DRISHTI_TRANSPORT=record python scripts/capture_fixtures.py --source shopify --merchant-shop test-store
```

Sets `RecordingTransport`, runs sync against the live API, writes responses to `fixtures/shopify/`, sanitizes PII via a configured rule set (regex replacements for emails, phone numbers, addresses), and updates `index.yaml`. We expect to run this once per source during the build.

### 7.3 Why this beats VCR cassettes

VCR cassettes are great for tests but bad for demo curation. With cassettes, you can't easily inspect or hand-craft a response that demonstrates "what happens when Shiprocket reports an RTO cluster." With the fixture system, fixtures are first-class artifacts — committable, editable, reviewable. We can deliberately seed `merchant_c` with an RTO cluster the agent will detect, and the evaluator can read the fixture to understand the test data.

VCR also doesn't help with the recording → sanitization step, which we needed anyway.

### 7.4 Why this beats env-flag mocks

Env-flag mocks (`if MOCK_MODE: return hardcoded_dict`) put fake responses inside the connector code, which:

- breaks the "swappable" requirement (transport isn't an interface, it's an `if`),
- doesn't exercise the connector's parsing/error-handling code paths,
- gives no way to demonstrate "the same code that runs against fixtures runs against live."

The Transport protocol gives us all three.

## 8. The mode toggle

Per-source, per-environment config. Default `MOCK` everywhere except where overridden. Examples:

```bash
# Demo deployment (all mock)
DRISHTI_SHOPIFY_TRANSPORT=mock
DRISHTI_SHIPROCKET_TRANSPORT=mock
DRISHTI_RAZORPAY_TRANSPORT=mock

# Live OAuth proof (Shopify only)
DRISHTI_SHOPIFY_TRANSPORT=live

# Production
DRISHTI_SHOPIFY_TRANSPORT=live
DRISHTI_SHIPROCKET_TRANSPORT=live
DRISHTI_RAZORPAY_TRANSPORT=live
```

This is checked into `.env.example` with the demo defaults so the evaluator can flip a single flag, point at a Shopify dev store, and watch the live OAuth path work end-to-end. Same connector code, same syncer code, same normalize code, same schema, same chat tools. Just a transport swap.

## 9. What this connector layer does not have, and why

- **No batching across connectors.** Each connector's sync is an independent job; cross-source coordination happens only at the schema layer (`order_links`). Cleaner failure isolation.
- **No Shopify GraphQL in v0.** Shopify's GraphQL Admin API is the production-best-practice path for new public apps, but the REST Admin API is simpler for a controlled v0 demo/custom-app flow. The README should call this out clearly.
- **No dead-letter queue at the connector layer.** Failed sync runs are logged with `status='failed'` and surface in the admin UI; manual retry triggers a new run. A proper DLQ with auto-retry policy is a v1 scale item.
- **No connector marketplace.** The brief asks for three; we shipped three. Adding a fourth is documented (§6); a runtime-loadable plugin system is feature creep for v0.
