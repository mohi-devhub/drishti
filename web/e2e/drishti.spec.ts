import { expect, test, type Page } from "@playwright/test";

const apiOrigin = "http://127.0.0.1:8787";

test.beforeEach(async ({ page }) => {
  await mockDemoAuth(page);
});

test("streams cited chat and pins aggregate evidence", async ({ page }) => {
  await page.route(`${apiOrigin}/chat/sessions`, async (route) => {
    await route.fulfill({ json: { sessions: [] } });
  });
  await page.route(`${apiOrigin}/chat/stream`, async (route) => {
    await route.fulfill({
      contentType: "text/event-stream",
      body: [
        sse("metadata", {
          session_id: "session_1",
          tool_results: [
            {
              rows: [
                {
                  row_id: "order:ord_1",
                  raw_record_id: "raw_1",
                  fetched_from: "orders",
                  values: { order_id: "ord_1", total_paise: 100000 },
                },
                {
                  row_id: "shipment:ship_1",
                  raw_record_id: "raw_2",
                  fetched_from: "shipments",
                  values: { shipment_id: "ship_1", freight_paise: 12000 },
                },
              ],
              aggregates: [
                {
                  agg_id: "agg_orders_total_paise",
                  label: "orders_total_paise",
                  value: 100000,
                  unit: "inr_paise",
                  derived_from_row_ids: ["order:ord_1", "shipment:ship_1"],
                  formula: "SUM(orders.total_paise)",
                },
              ],
            },
          ],
        }),
        sse("delta", { text: "Revenue is " }),
        sse("delta", { text: "<cite agg_orders_total_paise>₹1,000</cite>." }),
        sse("done", { answer: "Revenue is <cite agg_orders_total_paise>₹1,000</cite>." }),
      ].join(""),
    });
  });

  await page.goto("/chat");
  await page.getByPlaceholder("Ask about revenue, returns, shipments, or evidence").fill("total revenue");
  await page.getByRole("button", { name: "Send" }).click();

  await expect(page.getByText("Revenue is")).toBeVisible();
  await page.getByRole("button", { name: "₹1,000" }).click();
  await expect(page.getByText("orders_total_paise")).toBeVisible();
  await expect(page.getByText("order:ord_1")).toBeVisible();
  await expect(page.getByText("shipment:ship_1")).toBeVisible();
});

test("runs the agent and renders returned findings", async ({ page }) => {
  let findingsLoaded = false;
  let runPolls = 0;
  await page.route(`${apiOrigin}/api/findings**`, async (route) => {
    await route.fulfill({
      json: findingsLoaded
        ? {
            run: {
              id: "run_1",
              trigger: "manual",
              status: "completed",
              findings_count: 1,
              finished_at: "2026-05-16T08:00:00Z",
              created_at: "2026-05-16T07:59:00Z",
            },
            findings: [sampleFinding()],
          }
        : { run: null, findings: [] },
    });
  });
  await page.route(`${apiOrigin}/agents/rto_shipping_margin/duty-configs`, async (route) => {
    await route.fulfill({ json: { configs: [] } });
  });
  await page.route(`${apiOrigin}/agents/rto_shipping_margin/runs`, async (route) => {
    findingsLoaded = true;
    await route.fulfill({ json: { run_id: "run_1", status: "queued", findings_count: 0 } });
  });
  await page.route(`${apiOrigin}/agents/rto_shipping_margin/runs/run_1`, async (route) => {
    runPolls += 1;
    await route.fulfill({
      json: { run_id: "run_1", status: runPolls === 1 ? "running" : "completed", findings_count: 1 },
    });
  });

  await page.goto("/findings");
  await page.getByRole("button", { name: "Run agent" }).click();

  await expect(page.getByText("COD RTO pincode cluster").first()).toBeVisible();
  await expect(page.getByText("open").first()).toBeVisible();
  await expect(page.getByText("abc123")).toBeVisible();
});

test("switches between Merchant A, B, and C", async ({ page }) => {
  const requestedMerchants: string[] = [];
  await page.route(`${apiOrigin}/demo/token/*`, async (route) => {
    requestedMerchants.push(route.request().url().split("/").pop() || "");
    await route.fulfill({ json: { token: "demo-token", merchant_key: requestedMerchants.at(-1) } });
  });
  await page.route(`${apiOrigin}/api/findings**`, async (route) => {
    await route.fulfill({ json: { run: null, findings: [] } });
  });
  await page.route(`${apiOrigin}/agents/rto_shipping_margin/duty-configs`, async (route) => {
    await route.fulfill({ json: { configs: [] } });
  });

  await page.goto("/findings");
  const switcher = page.getByLabel("Demo merchant");
  await switcher.selectOption("merchant_a");
  await expect(page.getByText("Merchant A").first()).toBeVisible();
  await switcher.selectOption("merchant_b");
  await expect(page.getByText("Merchant B").first()).toBeVisible();
  await switcher.selectOption("merchant_c");
  await expect(page.getByText("Merchant C").first()).toBeVisible();

  expect(requestedMerchants).toEqual(expect.arrayContaining(["merchant_a", "merchant_b", "merchant_c"]));
});

async function mockDemoAuth(page: Page) {
  await page.route(`${apiOrigin}/demo/token/*`, async (route) => {
    const merchant = route.request().url().split("/").pop() || "merchant_c";
    await route.fulfill({ json: { token: "demo-token", merchant_key: merchant } });
  });
}

function sse(event: string, data: unknown) {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
}

function sampleFinding() {
  return {
    id: "finding_1",
    run_id: "run_1",
    duty: "cod_rto_risk",
    finding_type: "cod_rto_pincode_cluster",
    severity: "high",
    lifecycle_status: "open",
    fingerprint: "abc123",
    confidence: 0.91,
    evidence_row_ids: ["shipment:ship_1"],
    estimated_saving_inr_low: 1000,
    estimated_saving_inr_high: 2000,
    narrative: "High RTO risk.",
    narrative_status: "validated",
    proposed_action: { action_type: "require_prepaid_for_segment", parameters: { payment_method: "cod" } },
    citations: {},
    created_at: "2026-05-16T08:00:00Z",
  };
}
