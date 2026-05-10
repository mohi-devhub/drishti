# Drishti — Citation Contract

The brief: *"Every numerical claim in the answer carries a citation back to the source rows. Uncited numbers don't survive to the user."*

This document defines what "citation" means in Drishti, how the model expresses one, how the validator enforces the contract, what happens when validation fails, and how citations render in the UI. The citation contract is the load-bearing piece for the "chat grounding" rubric in the brief.

## 1. The core principle: the model cannot write numbers

The single most important architectural decision in this contract: the chat LLM and the agent LLM are not allowed to *generate* numeric values. They can only *reference* values that came back from a deterministic tool call earlier in the same turn.

Concretely: when a user asks *"how much did COD orders to pincode 1100XX cost in RTO last month?"*, the flow is:

1. The model calls `query_rto_losses(date_range=..., payment_method='cod', pincode_prefix='1100')`. The backend runs deterministic SQL. The result includes a row `{ agg_id: "agg_a91", label: "rto_loss_total", value: 3960, currency: "INR" }`.
2. The model writes its answer using `<cite agg_a91>` markers wrapping every number it references.
3. The validator confirms every number traces to an aggregate or row from this turn's tool results.

If the model wants to say *"₹4,500"*, but the only aggregate returned was *3,960*, the validator catches the mismatch. The model cannot fabricate a number that "looks right." This is the architecturally enforced version of the brief's *"no hallucinated values"* line.

The alternatives we considered and rejected:

- **Inline tags only, model-written citations.** Trusts the model to attach correct IDs. Fails: model hallucinates IDs that look real (`ord_8472`).
- **Structured response JSON with citation arrays.** Trusts the model to pair claims with sources. Fails: model confidently pairs ₹3,960 with three plausible-but-wrong order IDs.
- **Tool-call-only with system-validated attribution.** Mechanical to validate. The validator's job becomes: does this number exist in the tool transcript? Does this ID exist? Does the cited value match the displayed value? Three deterministic checks.

We picked the third.

## 2. Tool result schema

Every chat-layer and agent-layer tool returns a `ToolResult` with this shape:

```python
class ToolResult(BaseModel):
    result_id: str                         # e.g., "tr_5d8f2a..."
    tool_name: str
    args: dict                             # what the LLM passed (merchant_id is NEVER in here)
    rows: list[CitedRow]
    aggregates: list[CitedAggregate]
    metadata: dict                         # row counts, filters applied, freshness signals

class CitedRow(BaseModel):
    row_id: str                            # "order:ord_a91", "shipment:ship_b22", "payment:pay_c33"
    values: dict[str, Any]                 # the typed columns the LLM may reference
    source: str                            # 'shopify' | 'shiprocket' | 'razorpay'
    source_record_id: str                  # source's own ID
    raw_record_id: str                     # FK into source_records — the lineage anchor
    fetched_from: str                      # e.g., "GET /admin/api/2026-01/orders/5234567890123.json"
    synced_at: str                         # ISO timestamp
    sync_run_id: str                       # FK into sync_runs

class CitedAggregate(BaseModel):
    agg_id: str                            # e.g., "agg_a91..."
    label: str                             # e.g., "rto_loss_total_pincode_1100"
    value: int | float                     # the number itself
    unit: str                              # 'inr_paise' | 'count' | 'percent_basis_points' | ...
    derived_from_row_ids: list[str]        # the rows that fed this aggregate
    formula: str                           # short human-readable, e.g., "SUM(orders.total_paise WHERE ...)"
```

Three things to notice:

1. **Every row has a `row_id` formatted `<entity>:<id>`.** The prefix tells the validator which table to look up against. This is the citation grammar's primary key.
2. **Every aggregate carries `derived_from_row_ids`.** Citing an aggregate transitively cites the rows behind it. The drill-down UI walks this chain.
3. **`raw_record_id` lives on every row.** The full provenance chain (row → raw → endpoint → timestamp) is in the tool result itself; the validator doesn't need to re-fetch.

Tool results are immutable for the duration of a turn. Once `tr_5d8f2a` is returned, every later step reads it from the same in-memory turn state.

## 3. The `<cite>` marker grammar

The model is system-prompted to wrap every numeric claim in a `<cite>` marker. The grammar:

```
<cite ID>NUMBER</cite>                    one ID
<cite ID,ID,ID>NUMBER</cite>              multiple IDs (one number drawn from multiple rows)
<cite agg_a91>₹3,960</cite>               typical aggregate cite
<cite order:ord_a91>₹499</cite>           typical row cite
```

Two grammar rules:

- **IDs are either `agg_*` or `<entity>:<id>` row references.** Anything else is a parse error → uncited.
- **The `<cite>` content is the number as the user will see it**, formatted (currency symbol, commas, units). The validator extracts the bare numeric and compares.

The model's system prompt includes 3 worked examples and a hard rule: *"You MUST wrap every numeric value in a `<cite>` tag, including counts, currency amounts, percentages, and dates expressed numerically. If you cannot find an aggregate or row supporting a number, do not write it. Say 'I don't have data on that' instead."*

## 4. The validator — state machine

The validator runs after the model produces a candidate response, before any output reaches the user. It is purely synchronous and deterministic; no LLM in the validation loop.

```
                      [draft response from model]
                                │
                                ▼
                ┌──── PARSE: extract claims ────┐
                │                               │
                │  - find every <cite> tag      │
                │  - find every numeric token   │
                │    NOT inside a <cite>        │
                │                               │
                └──────────────┬────────────────┘
                               │
                               ▼
              ┌───── COVERAGE CHECK ─────┐
              │                          │
              │  any number outside      │
              │  a <cite>?               │
              │                          │
              │  yes → uncited_claims++  │
              │  no → continue           │
              │                          │
              └────────────┬─────────────┘
                           │
                           ▼
              ┌── EXISTENCE + VALUE CHECK ──┐
              │                             │
              │  for each <cite IDS>NUM</cite>:
              │    do all IDS exist in turn's tool results?
              │      no  → bad_cite++
              │    does NUM == cited.value (within format)?
              │      no  → bad_value++
              │                             │
              └────────────┬────────────────┘
                           │
                           ▼
              ┌──────── DECIDE ──────────┐
              │                          │
              │  bad_count == 0 → PASS   │
              │  first failure  → RETRY  │
              │  second failure → REDACT │
              │                          │
              └──────────────────────────┘
```

### 4.1 Coverage check

Numeric tokens are detected by a regex (currency-and-number-aware: `₹\d[\d,]*(?:\.\d+)?`, `\d[\d,]*\.?\d*%?`, dates like `\d{4}-\d{2}-\d{2}`). A number outside any `<cite>` tag is an uncited claim.

Two carve-outs from coverage (whitelisted tokens that don't require a cite):
- **Year mentions in prose** (e.g., "in 2025") — only when not adjacent to currency or unit.
- **Quantifiers in instructions** ("the top 3 reasons") that the model writes in *its own narrative*, not as a data claim.

The whitelist is small and explicit; everything else needs a cite.

### 4.2 Existence check

Every `<cite>` marker's IDs are looked up in `turn.tool_results`:

- `agg_*` IDs → must match an `agg_id` in some `ToolResult.aggregates` of this turn.
- `<entity>:<id>` row IDs → must match a `row_id` in some `ToolResult.rows` of this turn.

If the ID doesn't exist, it's a `bad_cite`. The model fabricated an ID.

### 4.3 Value check

For aggregate cites, the displayed number must equal `aggregate.value`, accounting for formatting:

- Currency: strip the symbol and commas, parse, compare in the smallest unit (paise) within tolerance 0. The model is forbidden from doing arithmetic; it must cite an aggregate that already has the answer.
- Counts: integer equality.
- Percentages: equality at one decimal place by default; the aggregate carries `unit` to drive this.

For row cites, the model must reference a specific value from `row.values`. The cite grammar extension `<cite order:ord_a91#total_paise>₹499</cite>` (with the `#field` suffix) is supported but optional — without `#field`, the validator scans `row.values` and accepts a match on any field. Worked examples in the prompt prefer the explicit form.

If `displayed_value != cited_value`, it's a `bad_value`. The model either did bad arithmetic or fabricated.

### 4.4 Decision: retry, then redact

On the **first** validation failure of a turn, the validator builds structured feedback for the model:

```
Your previous answer had validation issues:
- Uncited numbers (write nothing or wrap in <cite>): ['12 orders', '₹4,200']
- Cited IDs that don't exist: ['agg_xyz']
- Cited IDs whose value doesn't match what you wrote: ['agg_a91 has value 3960 but you wrote 3970']

Available tool results in this turn:
- tr_5d8f: query_rto_losses returned 1 aggregate (agg_a91 = 3960 INR) and 12 rows
- tr_8e2c: query_courier_freight returned 3 aggregates and 45 rows

Re-answer. Cite only the values above. If something cannot be cited, do not write it.
```

The model gets exactly one retry. Why one and not infinite: in practice, retry-2 almost always produces the same shape of failure, and we don't want a single turn looping for minutes. The retry budget is tracked per-turn.

On the **second** failure (after the retry), the validator falls back to **redact**:

- Every uncited number is replaced by `[uncited]` in the user-visible output.
- Every cite with a `bad_cite` or `bad_value` is replaced by `[uncited]`.
- A warning chip appears in the UI: *"Some values in this answer could not be verified and have been hidden. View raw."*
- The full failure detail is logged to `tool_calls.validation_failures` for eval analysis.

This is the safest real-world posture (the rubric question Mohith asked about). A founder seeing `[uncited]` knows what they don't know; a founder seeing `₹4,200` (made up) makes a decision against bad data. Redaction is louder than wrongness.

### 4.5 Auto-attach: the helpful path

There's one validator behavior that doesn't fail and doesn't retry: **auto-attach**.

If the model writes a number *without* a `<cite>` tag, and that number exactly matches one unambiguous value from a tool result in this turn's transcript, the validator inserts the appropriate `<cite>` and proceeds. If the same displayed number appears in multiple candidate rows or aggregates, auto-attach is disabled for that token and the normal retry/redaction path applies.

Auto-attach is logged separately from retries (`validation_status='passed'` but `auto_attached_count > 0`). Ambiguous auto-attach candidates are logged as validation failures. Eval runs surface auto-attach rate as a quality signal: too high means the model is sloppy with markup; zero means the prompt is doing its job.

## 5. What a citation resolves to (the full chain)

When the user hovers a citation footnote in the UI, they see:

```
Cite: agg_a91   "rto_loss_total_pincode_1100"   ₹3,960

  Computed from 12 source rows:
    1. order:ord_a91   ₹499   shopify   raw_record raw_b8e2 (GET /admin/api/2026-01/orders/5234567890123.json)
                                       fetched_at 2026-05-12T03:14Z   sync_run run_847
    2. order:ord_b22   ₹399   shopify   raw_record raw_8c1f ...
    ... 10 more ...

  [view raw API responses ▾]
```

The "view raw" expands to show the actual JSONB from `source_records`. The chain visible to the user is:

```
displayed number → aggregate → derived_from_row_ids → domain row → raw_record_id → source_records.payload + endpoint + timestamp
```

The point of this UX: the citation isn't a footnote in the academic sense ("this claim was made in this paper"). It's a literal lineage proof: *"this number was computed from these rows, which were normalized from this raw API response, which Shopify returned at this exact timestamp from this exact endpoint."* That's what an evaluator hovering a citation should see, and what the README will show in screenshots.

## 6. The chat-layer tools

Tools the chat LLM can call. All are read-only. All take args that **never include `merchant_id`** — the backend injects `merchant_id` from the Clerk session before executing.

| Tool | Purpose | Returns |
|---|---|---|
| `query_orders(filters)` | Filter orders by date, status, payment_method, pincode prefix, customer | rows + aggregates (count, total_paise, mean_total) |
| `query_shipments(filters)` | Filter shipments by date, status, courier_id, pincode | rows + aggregates (count by status, freight totals) |
| `query_payments(filters)` | Filter payments | rows + aggregates |
| `query_refunds(filters)` | Filter refunds | rows + aggregates |
| `query_rto_losses(date_range, group_by)` | Cross-source: orders ⨝ shipments ⨝ payments where shipment.status='rto_*' | aggregates by group_by (`pincode_cluster | courier | payment_method`) |
| `query_courier_freight(date_range, group_by)` | Per-courier freight cost and delivery rate | aggregates |
| `query_delayed_prepaid(as_of)` | Prepaid shipments past expected_delivery_at | rows |
| `query_refund_shipping_mismatches(date_range)` | Orders that were refunded after fulfillment-shipped | rows |
| `query_agent_findings(filters)` | Read agent's run history (so the chat can answer "what did the agent find this week?") | rows |
| `drill_down(row_id)` | Resolves `<entity>:<id>` to its raw_record JSONB | one row + raw payload |
| `time_now()` | Current time in merchant's TZ | one aggregate |

Three observations on this tool set:

1. **Each tool is a parameterized SQL query.** Implementations live in `app/tools/queries/`. They're version-controlled, testable, and never depend on LLM reasoning.
2. **No tool returns "raw rows from a domain table."** Every return shapes results into `rows + aggregates` with IDs. This is what makes citation possible.
3. **No tool mutates anything.** The chat LLM has zero write surface area. The brief's "reads and writes over the data" requirement is satisfied at the *system* level — sync writes data, the agent writes findings, webhooks write incoming data — but the LLM's tool surface is read-only by design. The README will note this distinction explicitly: writes happen via deterministic system paths; the LLM never decides to write.

## 7. The agent-layer tools

The agent reuses some chat tools (`query_rto_losses` etc.) and adds duty-specific ones (detailed in `AGENT.md`). The agent's tool registry is a *strict subset* of read-only tools, enforced at registration time:

```python
AGENT_TOOLS = TOOL_REGISTRY.subset(
    only_read_only=True,
    additional=[duty_specific_queries],
)
```

There is no path for the agent to call a write tool. A test (`tests/test_agent_tool_surface.py`) asserts every `AGENT_TOOLS` entry is annotated `@read_only` and any future tool that mutates state cannot be added without explicit override. This is mechanical enforcement of the brief's *"don't actually send anything"* line.

## 8. UI rendering

The frontend receives the validated response with `<cite>` markers intact. The renderer:

1. Parses the response into a token tree: text spans + cite spans.
2. For each cite span, replaces it with a `<CitedSpan>` React component that:
   - displays the cited number with the original formatting,
   - shows a small subscript number (1, 2, 3 ...) anchoring to a footnote panel,
   - on hover or tap, reveals an inline popover with the aggregate label, value, formula, and a "view rows" link,
   - on click of "view rows", expands a side panel with the row list and per-row "view raw" drill-down.
3. Shows the warning chip if any redactions happened, with a link to "Why was this hidden?" that explains the validator's failure mode.

The visual emphasis is deliberate: numbers in the answer are subtly different from prose (slightly heavier weight + an underdot), so the eye reads citation-density at a glance. A response with many cited numbers looks substantiated; a response with `[uncited]` tokens looks honestly limited.

## 9. Failure modes documented before the evaluator probes

In honesty-up-front form:

1. **Float precision.** Currency is paise (int). Percentages we compare at 1 dp by default. If we add tools that aggregate floats (rates, ratios) we'll need a tolerance config; not in v0.
2. **Date arithmetic.** The model cannot compute "two weeks ago." Instead, every relative-date tool argument is parsed by a deterministic helper before the SQL runs, and the date is *also* surfaced as an aggregate the model can cite. No hand-rolled date math reaches the user.
3. **Aggregation ambiguity.** "Average order value" could mean mean, median, p50. Tools surface `mean` and `median` as separate aggregates; the model picks one and cites it; the user can drill down to see the formula.
4. **Stale data.** Tools that join across sources include a `freshness` signal in `metadata`. If any source's last-sync is older than 6h, the freshness flag is set and the model is system-prompted to surface the stale-data caveat (cite-validated like everything else).
5. **Missing linkage.** When `order_links` is incomplete (e.g., a recent order has no shipment yet), cross-source aggregates exclude those rows and report `excluded_count` as an aggregate the model can cite. The user sees: *"₹3,960 in RTO losses across 12<cite agg_count> linked orders. 4<cite agg_excluded> recent orders are unlinked and excluded."*
6. **Validator escape: model invents an ID that happens to look real.** Caught by the existence check (we verify against the turn's actual results, not against a regex). A model citing `agg_xyz` when no `agg_xyz` exists in this turn → redacted.
7. **Validator escape: aggregate IDs collide across turns.** They don't — `agg_*` IDs are turn-scoped UUIDs, generated at tool-execution time. A previous turn's `agg_a91` is gone by the next turn.
8. **What the validator does NOT catch.** Qualitative claims. If the model writes *"COD orders are clearly the worst,"* the validator has nothing to check. The system prompt discourages qualitative absolutes, but the contract is a numerical contract; qualitative integrity is on the prompt.

## 10. Eval harness for citations

`tests/eval/citation_contract.py` runs a corpus of 30 question-and-expected-shape pairs:

```python
QUESTIONS = [
    ("How much did we lose to RTO last month?",     {"min_aggregates_cited": 1, "max_uncited": 0}),
    ("Which courier has the highest freight?",       {"min_rows_cited": 3,       "max_uncited": 0}),
    ("Are any prepaid shipments stuck?",             {"min_rows_cited": 0,       "max_uncited": 0}),  # 0 rows is ok
    ...
]
```

The eval runs the full turn (model + tools + validator) and asserts the output meets the expected shape. The corpus mixes:

- **Direct factual questions** with one obvious aggregate.
- **Cross-source questions** that exercise `order_links`.
- **Empty-result questions** ("are there any shipments to Antarctica?") — should produce a no-data answer with no fabricated numbers.
- **Adversarial questions** that try to lure the model into computing ("estimate next month's losses if RTO doubles") — should refuse or cite a stable aggregate, never fabricate.
- **Stale-data questions** with sync timestamps deliberately pushed >6h ago — should surface the freshness caveat.

Eval results are reported in the README under "Where it breaks" with the actual pass/fail counts, redacted-token counts, and auto-attach counts.

## 11. Summary

| Concern | Drishti's answer |
|---|---|
| Where do numbers come from? | Deterministic tool calls, never LLM generation. |
| How does the LLM mark a citation? | `<cite ID>NUMBER</cite>`, IDs are `agg_*` or `<entity>:<id>`. |
| What does the validator check? | Coverage, existence, value-match. |
| What if the model fails? | One structured retry; then redact uncited, log to eval. |
| What does a citation point at? | Aggregate → rows → raw_record_id → endpoint + timestamp. |
| Where can the LLM mutate state? | Nowhere. Tool surface is read-only by construction. |
| What's logged for audit? | Every tool call, every validation pass/fail, every redaction. |
| What's enforced mechanically vs. by prompt? | Number generation, ID existence, value match: mechanical. Qualitative honesty, prose tone: prompt. |
