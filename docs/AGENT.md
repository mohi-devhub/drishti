# Drishti — The Agent

> *"AI employees for D2C brands"* — the brief.

This document specifies Drishti's first AI employee: the **RTO + Shipping Margin Worker**. The brief is explicit about what it scores: *"Trigger, data, decision, action all explicit. Failure modes called out before we ask."* This document answers each.

## 1. Identity

The Worker is one entity with four duties, modeled after how a human ops analyst at a D2C brand actually thinks: *"Today I'll look at where shipping money is leaking — bad COD lanes, bad couriers, stuck packages, and refunds that didn't unship."* That framing produced four duties under a single run log, rather than four narrow agents.

| Property | Value |
|---|---|
| `agent_name` | `rto_shipping_margin_worker` |
| Cadence | Daily, 03:00 IST per merchant (staggered) + manual trigger |
| Scope | Shipping margin: RTO, courier choice, delivery timeliness, refund-shipping mismatches |
| Data dependencies | `orders`, `shipments`, `tracking_events`, `payments`, `refunds`, `order_links` |
| Tool surface | Read-only by construction (see §7) |
| Output | Run log with findings, evidence, ₹-savings estimates, proposed actions; **no external action execution** |

## 2. Why this employee, and not others

The brief asks "why this agent" be answered in the README. The reasoning:

- **Shipping margin is the single biggest unmonitored cost center for Indian D2C.** RTO rates of 25–40% on COD orders are common; couriers vary 30–50% in cost on the same lane; refunded-but-shipped orders are a quiet drain. A small percentage saved compounds against thousands of orders.
- **It exercises the cross-source schema the most.** RTO requires orders + shipments + payments. Courier-margin requires shipments + (linked orders for revenue context). Delayed-prepaid requires shipments + (linked payment status). Refund-shipping requires refunds + payments + shipments. If `order_links` works for this agent, it works for everything.
- **It's the right level of LLM judgment.** Each duty's *detection* is rule-based (deterministic SQL). The *narration and action recommendation* benefits from LLM judgment (severity ranking from evidence, action phrasing in operator-friendly language). That's the deterministic-then-LLM split that makes the agent both reliable and useful.
- **It produces ₹-denominated findings.** Not "you have a problem with RTO" but "₹3,200–₹4,400 / month in RTO loss on this pincode cluster." That's what an operator can act on.

What we did not pick:

- **An inventory restock agent.** Would need product/inventory data we don't sync, and is too easily-confused with a forecasting problem.
- **A customer-segmentation agent.** Drifts into marketing territory, not ops; harder to validate ₹-impact.
- **A pricing agent.** Out of scope; pricing decisions need competitive data we don't have.
- **A fulfillment-routing agent.** Would need to *write* to Shopify or Shiprocket, which the brief explicitly forbids in v0.

The Worker stays read-only, ops-focused, and ₹-quantified — the highest-signal slice of "AI employee" we can ship in 7 days.

## 3. The four duties

Each duty has the same shape:

- **Trigger** — what conditions cause the duty to look at data
- **Detection SQL** — the deterministic query (parameterized, version-controlled)
- **Finding output** — the structured result of detection
- **LLM narration** — what the model adds to the finding
- **Proposed action** — the structured recommendation
- **Failure modes** — duty-specific edge cases

### 3.1 Duty: `cod_rto_risk`

**Trigger:** Daily, scans the trailing 30 days of COD orders that have a linked shipment.

**Question:** *Are there pincode clusters where COD orders are RTO-ing at a margin-negative rate?*

**Detection SQL** (sketch — full SQL in `app/agent/duties/cod_rto_risk.sql`):

```sql
WITH cod_orders AS (
  SELECT o.id AS order_id, o.placed_at, o.total_paise, o.shipping_pincode,
         LEFT(o.shipping_pincode, 4) AS pincode_cluster,
         s.id AS shipment_id, s.status AS shipment_status,
         s.freight_paise
  FROM orders o
  JOIN order_links ol ON ol.order_id = o.id AND ol.confidence >= 0.8
  JOIN shipments s ON s.id = ol.shipment_id
  WHERE o.merchant_id = current_setting('app.current_merchant_id')::uuid
    AND o.payment_method = 'cod'
    AND o.placed_at >= NOW() - INTERVAL '30 days'
    AND o.total_paise < 50000  -- under ₹500 threshold (configurable per merchant)
),
cluster_stats AS (
  SELECT pincode_cluster,
         COUNT(*) AS order_count,
         COUNT(*) FILTER (WHERE shipment_status LIKE 'rto_%') AS rto_count,
         SUM(freight_paise) FILTER (WHERE shipment_status LIKE 'rto_%') * 2 AS rto_freight_loss_paise,
         SUM(total_paise) FILTER (WHERE shipment_status LIKE 'rto_%') AS rto_revenue_loss_paise
  FROM cod_orders
  GROUP BY pincode_cluster
  HAVING COUNT(*) >= 5  -- minimum evidence
)
SELECT pincode_cluster,
       order_count,
       rto_count,
       (rto_count::numeric / order_count) AS rto_rate,
       rto_freight_loss_paise + (rto_freight_loss_paise * 0.4) AS estimated_loss_paise_low,
       rto_freight_loss_paise + (rto_freight_loss_paise * 0.6) AS estimated_loss_paise_high,
       array_agg(...) AS evidence_order_ids,
       array_agg(...) AS evidence_shipment_ids
FROM cluster_stats c JOIN cod_orders o USING (pincode_cluster)
WHERE c.rto_rate >= 0.40
GROUP BY c.pincode_cluster, c.order_count, c.rto_count, c.rto_freight_loss_paise
HAVING SUM(rto_freight_loss_paise) >= 100000;  -- ≥ ₹1000 minimum savings worth flagging
```

The thresholds (`<₹500 order`, `<5 orders evidence`, `>=40% RTO rate`, `>=₹1000 savings`) are constants in the SQL file with rationale comments. They were chosen to suppress noise; in production they'd be merchant-configurable, but in v0 they're fixed and called out in the README.

**Finding output:**

```python
Finding(
  duty='cod_rto_risk',
  finding_type='cod_rto_pincode_cluster',
  severity='high' if estimated_loss > 5000 else 'medium',
  confidence=min(1.0, evidence_count / 20),  # caps at 1.0 with 20+ orders evidence
  evidence_row_ids=['order:ord_a91', 'order:ord_b22', ..., 'shipment:ship_x44', ...],
  estimated_saving_inr_low=3200,
  estimated_saving_inr_high=4400,
  metadata={
    'pincode_cluster': '1100',
    'order_count': 18,
    'rto_count': 9,
    'rto_rate_pct': 50.0,
  },
)
```

**LLM narration prompt skeleton:**

```
You are narrating a finding from Drishti's RTO + Shipping Margin Worker.
Finding type: cod_rto_pincode_cluster.
Structured data: {finding json}.
Tool results available for citation: {turn_tool_results}.

Write a 2-3 sentence narrative for the merchant founder.
- Cite every number as <cite agg_id> or <cite row_id>.
- Do not write any number that isn't in the tool results.
- Then propose ONE action as JSON: {action_type, parameters, rationale}.
  Allowed action_types: ['require_prepaid_for_segment', 'add_manual_confirm_call', 'increase_cod_threshold'].
- Pick the action whose parameters best fit the finding.
```

**Proposed action shape:**

```python
{
  "action_type": "require_prepaid_for_segment",
  "parameters": {
    "segment": {"payment_method": "cod", "pincode_prefix": "1100", "max_order_paise": 50000},
    "rationale_short": "RTO rate 50% on this cluster, freight cost not recovered",
  },
  "rationale": "<full LLM-written rationale, citation-validated>",
}
```

**Failure modes:**

- **Stale shipment data.** If `shipments.synced_at < NOW() - 6h`, RTO rates may be stale. Duty checks freshness; if stale, finding's `confidence` is downgraded by 0.3 and the narrative includes a stale-data caveat.
- **New pincode (no history).** Clusters with `<5` orders are excluded — the threshold is enforced in SQL. The `agent_runs.duties_skipped` records the count of clusters skipped for this reason.
- **Single-vendor pincode.** If 100% of evidence orders shipped via a single courier, the finding could be courier-specific rather than COD-specific. Narrative is constrained to mention this; action recommendation defaults to the more conservative "manual_confirm_call" rather than "require_prepaid".

### 3.2 Duty: `courier_margin_drift`

**Trigger:** Daily; scans trailing 30 days of shipments grouped by (courier_id, route).

**Question:** *Is one courier disproportionately expensive or slow on a route compared to the alternatives?*

**Detection SQL** (sketch):

```sql
WITH courier_route_stats AS (
  SELECT s.courier_id, s.courier_name,
         LEFT(s.pickup_pincode, 3) || '_' || LEFT(s.delivery_pincode, 3) AS route,
         COUNT(*) AS shipment_count,
         AVG(s.freight_paise::numeric / NULLIF(s.weight_grams, 0)) AS avg_freight_per_g,
         PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (s.delivered_at - s.picked_up_at))/86400) AS p50_delivery_days,
         COUNT(*) FILTER (WHERE s.status LIKE 'rto_%') AS rto_count
  FROM shipments s
  WHERE s.merchant_id = current_setting('app.current_merchant_id')::uuid
    AND s.picked_up_at >= NOW() - INTERVAL '30 days'
    AND s.weight_grams > 0
  GROUP BY s.courier_id, s.courier_name, route
  HAVING COUNT(*) >= 5
),
route_baselines AS (
  SELECT route,
         MIN(avg_freight_per_g) AS best_freight_per_g,
         MIN(p50_delivery_days) AS best_p50_days
  FROM courier_route_stats
  GROUP BY route
  HAVING COUNT(DISTINCT courier_id) >= 2  -- need ≥2 couriers to compare
)
SELECT crs.*,
       rb.best_freight_per_g,
       crs.avg_freight_per_g - rb.best_freight_per_g AS freight_premium,
       crs.p50_delivery_days - rb.best_p50_days AS delivery_days_premium
FROM courier_route_stats crs
JOIN route_baselines rb USING (route)
WHERE (crs.avg_freight_per_g >= rb.best_freight_per_g * 1.25  -- 25% premium
       OR crs.p50_delivery_days >= rb.best_p50_days + 2)      -- 2+ days slower
  AND crs.shipment_count >= 5;
```

**Finding output:** one row per (courier, route) with quantified premium.

**LLM narration:** *"Bluedart on the BLR→DEL route is costing you 28% more per gram than Delhivery, with similar delivery times. Over 47 shipments last month that's ₹X overhead."* + action proposal `switch_default_courier_for_route`.

**Failure modes:**

- **Single-courier route (no comparison possible).** Excluded by the `HAVING COUNT(DISTINCT courier_id) >= 2` filter. Counted in `duties_skipped` reasons.
- **Weight outliers.** Heavy/light items on a route distort `avg_freight_per_g`. The duty filters `weight_grams > 0` and uses median elsewhere; outliers above 99th-percentile-by-weight per route are excluded.
- **Cold start (< 30 days of shipping data).** If `MAX(picked_up_at) - MIN(picked_up_at) < 14 days`, the duty produces no findings, logs `cold_start` in `duties_skipped`. We don't recommend courier switches without two weeks of evidence.

### 3.3 Duty: `delayed_prepaid`

**Trigger:** Daily; scans non-terminal shipments.

**Question:** *Which prepaid shipments have blown past their expected delivery date and need merchant attention?*

**Detection SQL** (sketch):

```sql
SELECT s.id AS shipment_id, s.awb_code, s.courier_name,
       s.expected_delivery_at, s.status,
       o.id AS order_id, o.total_paise, o.placed_at,
       p.status AS payment_status,
       NOW() - s.expected_delivery_at AS days_overdue
FROM shipments s
JOIN order_links ol ON ol.shipment_id = s.id AND ol.confidence >= 0.8
JOIN orders o ON o.id = ol.order_id
JOIN payments p ON p.id = ol.payment_id
WHERE s.merchant_id = current_setting('app.current_merchant_id')::uuid
  AND s.status NOT IN ('delivered', 'cancelled', 'rto_delivered', 'lost')
  AND s.expected_delivery_at < NOW() - INTERVAL '2 days'
  AND p.status = 'captured'  -- prepaid only
  AND o.total_paise >= 100000  -- ≥ ₹1000, otherwise the followup cost > value
ORDER BY days_overdue DESC
LIMIT 50;
```

**Finding output:** one finding per delayed shipment (not aggregated). These are individual escalations, not patterns.

**LLM narration:** *"Order #1234 (₹1,500) has been with Delhivery since May 1. Expected delivery May 4; today is May 10. Customer has paid; courier shows no movement since May 6."* + action `escalate_to_courier_support` or `notify_customer_proactively`.

**Failure modes:**

- **Carrier silence.** A shipment with no tracking events for >5 days could be lost or just unreported. The duty includes `last_tracking_event_at` in the metadata; the LLM is prompted to call out the distinction (and never to claim "lost" without evidence).
- **Recipient-caused delay.** Some delays are recipient-side (failed delivery attempts, address issues). The duty looks at `tracking_events` for `undelivered` or `delivery_attempted` events and downgrades severity for those — a redelivery isn't a vendor failure.
- **Volume spike.** During sale events, expected_delivery_at may be optimistic across the board. If >20% of all active shipments are flagged, the duty produces a *meta-finding* ("widespread delivery slowdown detected — likely volume-related, not courier-specific") instead of N individual findings. Threshold and behavior documented in the SQL comments.

### 3.4 Duty: `refund_shipping_mismatch`

**Trigger:** Daily; scans the trailing 60 days of refunds.

**Question:** *Were any orders refunded after they shipped, where we paid freight on something that came back?*

**Detection SQL** (sketch):

```sql
SELECT r.id AS refund_id, r.amount_paise AS refund_amount,
       p.id AS payment_id, p.amount_paise AS payment_amount,
       o.id AS order_id, o.placed_at,
       s.id AS shipment_id, s.status AS shipment_status, s.freight_paise,
       s.picked_up_at, r.processed_at AS refunded_at
FROM refunds r
JOIN payments p ON p.id = r.payment_id
JOIN order_links ol ON ol.payment_id = p.id AND ol.confidence >= 0.8
JOIN orders o ON o.id = ol.order_id
JOIN shipments s ON s.id = ol.shipment_id
WHERE r.merchant_id = current_setting('app.current_merchant_id')::uuid
  AND r.processed_at >= NOW() - INTERVAL '60 days'
  AND s.picked_up_at IS NOT NULL                -- shipped before refund
  AND s.picked_up_at < r.processed_at
  AND s.status NOT IN ('rto_delivered', 'rto_initiated', 'rto_in_transit')
       -- exclude legitimate "returned, refunded" path
ORDER BY (r.amount_paise + s.freight_paise) DESC;
```

**Finding output:** one finding per mismatched order, with the loss decomposed: refund amount + freight wasted.

**LLM narration:** *"Order #5678 was refunded ₹2,500 on May 5, but had already shipped via Delhivery on May 3 (₹120 freight). Total exposure: ₹2,620. The shipment didn't return as RTO, suggesting the customer kept the product or the goodwill refund was issued anyway."* + action `review_refund_policy_for_shipped_orders` or `check_courier_for_undelivered_pickup`.

**Failure modes:**

- **Partial refunds for damaged-in-transit goods.** A legitimate operator-initiated refund where the goods stayed with the customer. The duty flags the case but the LLM is prompted to surface this as a *review* rather than an *error* — the action is a review action, not a remediation.
- **Time skew.** Race conditions where a refund processes before the courier marks RTO can produce false positives. The duty's `s.status NOT IN (rto_*)` filter is the primary mitigation, but real systems can lag. Findings include the `picked_up_at` and `refunded_at` timestamps in evidence so the merchant can see for themselves.
- **Linkage gap.** If `order_links.payment_id IS NULL` (COD-only payment, refunds rare), the order is excluded from this duty. Counted in `duties_skipped`.

## 4. Trigger model

Two paths, same code:

### 4.1 Scheduled (production cadence)

Arq cron job `agent_daily_run`, scheduled at 03:00 IST. To avoid the thundering-herd problem at scale (10k merchants all running at 03:00):

```python
async def agent_daily_run(ctx, merchant_id: UUID):
    # Each merchant's actual run time = 03:00 + hash(merchant_id) % 4_hours
    delay = (hash(merchant_id) % 14400)  # 0..14399 seconds
    await asyncio.sleep(delay)
    await run_worker(merchant_id, trigger='scheduled')
```

The Arq scheduler enqueues `agent_daily_run` for every active merchant at 03:00; each worker self-staggers within a 4-hour window. This is built; the load harness measures the spread.

### 4.2 Manual

`POST /agents/{merchant_id}/runs` triggers an immediate run via `agent_worker`. Returns the `run_id` for polling. Used by the demo UI's "Run agent now" button.

Both paths converge on `run_worker(merchant_id, trigger=...)`. The run log records the trigger, but no other behavior differs. The evaluator clicking "Run agent" sees the same artifact a 03:00 cron would produce.

## 5. Run lifecycle

```
run_worker(merchant_id, trigger)
  │
  │ create agent_runs row (status=running, started_at)
  │
  │ snapshot input:
  │   for each source: last_synced_at, row_counts, freshness_ok
  │   record in agent_runs.input_snapshot
  │
  │ for duty in [cod_rto_risk, courier_margin_drift, delayed_prepaid, refund_shipping_mismatch]:
  │   try:
  │     check duty's required-source freshness
  │     if stale (>6h): record duties_skipped[duty]={'reason': 'stale_data', 'staleness': '...'}
  │     else:
  │       findings = await detect(duty)              # deterministic SQL
  │       for finding in findings:
  │         narration = await narrate(finding)        # LLM call, citation-validated
  │         persist agent_findings row
  │   except Exception as e:
  │     record errors[duty] = stack_trace
  │     continue                                     # one duty's failure doesn't kill the run
  │
  │ update agent_runs (status=completed|partial, finished_at, findings_count, errors)
  │
  │ no external action is taken; no email, webhook, or write call to any source.
```

`status='partial'` means at least one duty errored or was skipped. Run isn't a binary success/failure.

## 6. Run-log shape (the artifact the evaluator inspects)

`agent_runs` row + `agent_findings` rows render in the `/agent` UI as:

```
Run #847    started 2026-05-12 03:14    completed 2026-05-12 03:17    trigger: scheduled
Status: completed   |   4 duties run   |   3 findings

Input snapshot:
  shopify     fresh   1,247 orders   last_synced 2026-05-12 02:48
  shiprocket  fresh     893 shipments last_synced 2026-05-12 02:55
  razorpay    fresh   1,180 payments  last_synced 2026-05-12 02:51
  order_links 1,235 / 1,247 orders linked (12 unlinked, recent)

Duties:
  ✓ cod_rto_risk            1 finding   ⚠ medium severity
  ✓ courier_margin_drift    1 finding   ⚠ high severity
  ✓ delayed_prepaid         1 finding   ⚠ medium severity
  ✓ refund_shipping_mismatch 0 findings   no issues

Findings:
  1. [cod_rto_risk]   COD orders to pincode cluster 1100XX RTO rate 50%
                      Estimated savings: ₹3,200 - ₹4,400 / month
                      Evidence: 18 orders, 9 RTOs   [view evidence]
                      Proposed action: require_prepaid_for_segment
                      Narrative status: validated   [view full narrative]
  2. ...
```

Every number in the rendering is citation-validated. The evidence and narrative panels open the citation drill-down (same UI as chat-layer citations).

## 7. The read-only invariant

The brief: *"don't actually send anything; we want the run log and the reasoning."*

This is enforced mechanically for external side effects, not just in policy:

```python
AGENT_TOOLS = ToolRegistry(
    tools=[
        # Read-only chat tools the agent reuses
        query_orders, query_shipments, query_payments, query_refunds,
        query_rto_losses, query_courier_freight, query_delayed_prepaid,
        query_refund_shipping_mismatches,
        drill_down, time_now,

        # Duty-specific read-only tools
        detect_cod_rto_risk, detect_courier_margin_drift,
        detect_delayed_prepaid, detect_refund_shipping_mismatch,

        # Internal persistence tool; writes only to Drishti-owned audit tables
        persist_finding,
    ],
    enforce_read_only_external=True,
)
```

The registry validates at registration time:

1. Every tool is decorated with `@read_only_external` (asserts: no HTTP calls to source SaaS, no writes to external systems).
2. `persist_finding` is the only write tool, scoped to internal tables only (`agent_findings`, `agent_runs`).
3. A test (`tests/test_agent_tool_surface.py`) asserts the registry's full tool list and would fail loudly if any external-write tool were added.

The agent has no path — by code, not just policy — to send an email, post a webhook, or call a Shopify mutation. It can write only its internal run log and findings. v1 will add an action-execution layer; v0 is externally read-only by construction, and that's part of the README's narrative.

## 8. Failure modes (consolidated, before evaluator probes)

Documented across the duties above plus these system-level ones:

1. **Stale data in any source (>6h).** Affected duties are skipped with `reason='stale_data'`; the run continues with available sources. Surfaced in the input_snapshot of the run log.
2. **Insufficient evidence (<5 rows for a finding).** Finding is suppressed entirely. Counted in `duties_skipped`.
3. **Unlinked orders.** Orders with no shipment or no payment linkage are excluded from cross-source duties. Counts surfaced as aggregates the LLM cites.
4. **LLM narration validation failure.** If the citation validator can't pass after one retry, the finding's `narrative_status='degraded'`; it's stored with structured-only view (no prose). Never silently dropped.
5. **Estimate uncertainty.** Savings estimates are ranges (`estimated_saving_inr_low/high`) when underlying SQL stddev exceeds threshold. No false-precision point estimates.
6. **Per-duty failure isolation.** One duty erroring (SQL exception, LLM API timeout) doesn't fail the run. The error is recorded; other duties continue. Run status becomes `partial`.
7. **No external actions ever fire.** Enforced at the tool-registry level; tested.

## 9. Eval honesty for the agent

What we know breaks (or might) before the evaluator finds it:

- **Cold-start merchants** (less than 14 days of data) get the `cold_start` skip on `courier_margin_drift`, may produce no findings on `cod_rto_risk`. The run log shows the skips clearly.
- **Threshold tuning is constants in v0.** Production would expose merchant-level overrides for `cod_threshold_paise`, `min_evidence_count`, `rto_rate_floor`. v0 ships defaults that are reasonable for an Indian D2C merchant in the ₹500-orders-or-less COD segment but won't fit every business.
- **Pincode clustering is 4-digit-prefix only.** Real Indian pincodes have hierarchical structure (PIN code → sorting district → state) that finer-grained clustering would exploit. v0 keeps it simple and the README documents the upgrade path.
- **`courier_margin_drift` doesn't account for service quality.** A cheaper courier with worse delivery rates may not be the right switch; the duty surfaces the cost premium and the delivery-time premium separately, but the LLM narration weighting is heuristic.
- **`refund_shipping_mismatch` produces some operator-acceptable findings** (deliberate goodwill refunds where the customer kept the goods). The narrative frames these as "review" not "error," but the finding still appears. We'd add a `acceptable_loss` filter in v1 once we have merchant-side classification of refund reasons.
- **No multi-merchant pattern detection.** A courier that's bad at one merchant might be bad across many; v0 doesn't aggregate cross-merchant. Privacy concerns aside, the architecture supports it (queries scoped by merchant_id; an admin-tier role could aggregate). Deferred.

The README's "where it breaks" section will list the actual run results: how many findings on each demo merchant, how many degraded narrations, how many duties skipped — full transparency.

## 10. What "another week" would add to the agent

For the README's "what you'd do with another week" section, in priority order:

1. **Action execution scaffolding** — a write layer separate from the read-only tool registry, where each action_type maps to a specific Shopify/Shiprocket/Razorpay API call. Behind a manual-approve gate per finding. The agent proposes; the merchant approves; the executor fires.
2. **Per-merchant threshold tuning** — a settings UI for the four duties' constants, plus a "what if I'd used these thresholds last month" backtest.
3. **Cross-merchant courier benchmarking** — opt-in aggregation of courier performance across the merchant base, surfaced as "you're using Bluedart on this route, but 73% of similar merchants use Delhivery for it." Requires careful privacy design.
4. **A second AI employee** — a Customer Refund Risk Worker that watches order/refund patterns and proposes review queues. Demonstrates the agent registry pattern at a v1 scale.
5. **Forecasting on top of detection** — "given trailing 30-day RTO trend, expect ₹X loss next month if nothing changes." Requires statistical care; deferred for that reason.

These are the things the agent shape supports cleanly. The agent isn't a v1 wall; it's a v0 floor.
