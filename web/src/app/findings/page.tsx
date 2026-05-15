"use client";

import { useCallback, useMemo, useState } from "react";
import { AppHeader, CitationText, apiBase, authHeaders, labels, useDemoAuth } from "../components";
import type { MerchantKey } from "../components";

type Finding = {
  id: string;
  duty: string;
  finding_type: string;
  severity: string;
  confidence: number;
  evidence_row_ids: string[];
  estimated_saving_inr_low: number | null;
  estimated_saving_inr_high: number | null;
  narrative: string | null;
  narrative_status: string;
  proposed_action: Record<string, unknown>;
  created_at: string;
};

type AgentRun = {
  id: string;
  trigger: string;
  status: string;
  findings_count: number;
  finished_at: string | null;
  created_at: string | null;
};

type AgentRunResponse = {
  run_id: string;
  status: string;
  findings_count: number;
};

type ProposedAction = {
  action_type?: string;
  parameters?: Record<string, unknown>;
  rationale_short?: string;
  rationale?: string;
};

export default function FindingsPage() {
  const auth = useDemoAuth();
  const { refresh } = auth;
  const [findings, setFindings] = useState<Finding[]>([]);
  const [run, setRun] = useState<AgentRun | null>(null);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("Ready to run");
  const [selected, setSelected] = useState<string | null>(null);

  const load = useCallback(async (): Promise<boolean> => {
    if (!auth.token) return false;
    try {
      const response = await fetch(`${apiBase()}/api/findings`, { headers: authHeaders(auth.token) });
      const payload = await response.json();
      if (!response.ok) throw new Error(JSON.stringify(payload));
      setFindings(payload.findings || []);
      setRun(payload.run || null);
      setSelected((current) => current || payload.findings?.[0]?.id || null);
      setStatus(payload.run ? latestRunLabel(payload.run) : "Run completed with no findings");
      return true;
    } catch {
      setStatus("API unavailable");
      return false;
    }
  }, [auth.token]);

  async function runAgent() {
    setBusy(true);
    setStatus("Running");
    try {
      const response = await fetch(`${apiBase()}/agents/rto_shipping_margin/runs`, {
        method: "POST",
        headers: authHeaders(auth.token),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(JSON.stringify(payload));
      const completed = await pollAgentRun(payload.run_id);
      setStatus(`Latest run: ${completed.findings_count} findings`);
      setBusy(false);
      setSelected(null);
      void load();
    } catch (error) {
      console.error(error);
      const loaded = await load();
      if (!loaded) setStatus("Run failed");
      setBusy(false);
    } finally {
      setBusy(false);
    }
  }

  async function pollAgentRun(runId: string): Promise<AgentRunResponse> {
    for (let attempt = 0; attempt < 60; attempt += 1) {
      const response = await fetch(`${apiBase()}/agents/rto_shipping_margin/runs/${runId}`, {
        headers: authHeaders(auth.token),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(JSON.stringify(payload));
      if (!["queued", "running"].includes(payload.status)) return payload;
      setStatus(payload.status === "queued" ? "Queued" : "Running");
      await new Promise((resolve) => window.setTimeout(resolve, 1500));
    }
    throw new Error("Agent run timed out");
  }

  const switchMerchant = useCallback(
    (merchant: MerchantKey) => {
      setFindings([]);
      setRun(null);
      setSelected(null);
      setStatus("Ready to run");
      void refresh(merchant);
    },
    [refresh],
  );

  const active = findings.find((finding) => finding.id === selected) || findings[0] || null;
  const summary = useMemo(() => {
    const high = findings.filter((finding) => finding.severity === "high").length;
    const savingsLow = findings.reduce((total, finding) => total + (finding.estimated_saving_inr_low || 0), 0);
    const savingsHigh = findings.reduce((total, finding) => total + (finding.estimated_saving_inr_high || 0), 0);
    return { high, savingsLow, savingsHigh };
  }, [findings]);

  return (
    <main className="min-h-screen text-white">
      <AppHeader
        merchant={auth.merchant}
        token={auth.token}
        error={auth.error}
        authMode={auth.authMode}
        onMerchant={switchMerchant}
      />
      <section className="mx-auto grid max-w-7xl gap-5 px-5 py-6">
        <div className="overflow-hidden rounded-lg border border-white/10 bg-white/[0.035] p-6 shadow-2xl shadow-black/40">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <p className="text-xs font-medium uppercase tracking-[0.3em] text-white/35">{labels[auth.merchant]}</p>
              <h1 className="mt-2 text-4xl font-semibold tracking-[-0.05em]">Agent findings</h1>
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <button
                onClick={runAgent}
                disabled={busy || !auth.token}
                className={`h-10 rounded-full px-5 text-sm font-semibold transition disabled:cursor-not-allowed ${
                  busy ? "bg-emerald-200/15 text-emerald-50 ring-1 ring-emerald-200/35" : "bg-white text-black hover:bg-emerald-100"
                }`}
              >
                {busy ? "Running..." : run ? "Run agent again" : "Run agent"}
              </button>
            </div>
          </div>
          <p className="mt-3 text-sm text-white/45">{status}</p>
          <div className="mt-5 grid gap-3 sm:grid-cols-3">
            <Metric label="Total" value={String(findings.length)} />
            <Metric label="High severity" value={String(summary.high)} />
            <Metric label="Savings range" value={`${money(summary.savingsLow)} - ${money(summary.savingsHigh)}`} />
          </div>
        </div>

        <div className="grid gap-5 xl:grid-cols-[440px_minmax(0,1fr)]">
          <section className="overflow-hidden rounded-lg border border-white/10 bg-white/[0.035] shadow-2xl shadow-black/30">
            <div className="border-b border-white/10 bg-black/25 px-4 py-3">
              <h2 className="text-sm font-semibold">Finding queue</h2>
            </div>
            <div className="max-h-[calc(100vh-290px)] min-h-96 overflow-auto p-2">
              {findings.map((finding) => (
                <button
                  key={finding.id}
                  onClick={() => setSelected(finding.id)}
                  className={`mb-2 block w-full rounded-md border p-3 text-left transition ${
                    active?.id === finding.id
                      ? "border-emerald-200/40 bg-emerald-200/10"
                      : "border-white/10 bg-black/20 hover:bg-white/[0.05]"
                  }`}
                >
                  <div className="flex items-center justify-between gap-3">
                    <span className={`rounded px-2 py-0.5 text-xs font-semibold ${severityClass(finding.severity)}`}>
                      {finding.severity}
                    </span>
                    <span className="text-xs font-medium text-white/45">{Math.round(finding.confidence * 100)}%</span>
                  </div>
                  <p className="mt-3 text-sm font-semibold text-white">{titleize(finding.finding_type)}</p>
                  <p className="mt-2 text-xs uppercase tracking-[0.22em] text-white/35">{finding.duty}</p>
                  <div className="mt-3 flex items-center justify-between text-xs text-white/50">
                    <span>{finding.evidence_row_ids.length} evidence rows</span>
                    <span>{money(finding.estimated_saving_inr_low)} - {money(finding.estimated_saving_inr_high)}</span>
                  </div>
                </button>
              ))}
              {findings.length === 0 ? (
                <div className="grid min-h-72 place-items-center rounded-md border border-dashed border-white/15 bg-black/20 p-6 text-center text-sm text-white/45">
                  No findings yet for this merchant.
                </div>
              ) : null}
            </div>
          </section>

          <section className="overflow-hidden rounded-lg border border-white/10 bg-white/[0.035] shadow-2xl shadow-black/30">
            {active ? (
              <article>
                <div className="border-b border-white/10 bg-black/25 p-5">
                  <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                    <div>
                      <div className="flex flex-wrap items-center gap-2">
                        <span className={`rounded px-2 py-0.5 text-xs font-semibold ${severityClass(active.severity)}`}>
                          {active.severity}
                        </span>
                        <span className="text-xs font-medium uppercase tracking-[0.22em] text-white/35">{active.duty}</span>
                      </div>
                      <h2 className="mt-3 text-3xl font-semibold tracking-[-0.04em]">{titleize(active.finding_type)}</h2>
                    </div>
                    <div className="rounded-md border border-white/10 bg-white/[0.05] px-3 py-2 text-sm">
                      <span className="text-white/45">Confidence </span>
                      <span className="font-semibold">{Math.round(active.confidence * 100)}%</span>
                    </div>
                  </div>
                </div>
                <div className="grid gap-4 p-5 lg:grid-cols-3">
                  <Metric label="Savings low" value={money(active.estimated_saving_inr_low)} />
                  <Metric label="Savings high" value={money(active.estimated_saving_inr_high)} />
                  <Metric label="Evidence rows" value={String(active.evidence_row_ids.length)} />
                </div>
                {active.narrative ? (
                  <div className="border-y border-emerald-200/15 bg-emerald-200/10 p-5">
                    <p className="text-sm leading-7 text-white/75">
                      <CitationText text={active.narrative} />
                    </p>
                  </div>
                ) : null}
                <div className="grid gap-4 p-5 lg:grid-cols-2">
                  <CodePanel title="Evidence row IDs" value={active.evidence_row_ids} />
                  <ActionPanel action={active.proposed_action as ProposedAction} />
                </div>
              </article>
            ) : (
              <div className="grid min-h-96 place-items-center p-8 text-center text-sm text-white/45">
                Run the agent to populate findings.
              </div>
            )}
          </section>
        </div>
      </section>
    </main>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-white/10 bg-white/[0.055] p-4">
      <p className="text-xs font-medium uppercase tracking-[0.22em] text-white/35">{label}</p>
      <p className="mt-2 min-h-7 text-lg font-semibold text-white">{value}</p>
    </div>
  );
}

function CodePanel({ title, value }: { title: string; value: unknown }) {
  return (
    <div className="rounded-md border border-white/10 bg-black/25">
      <div className="border-b border-white/10 px-3 py-2 text-xs font-semibold uppercase tracking-[0.22em] text-white/35">{title}</div>
      <pre className="max-h-72 overflow-auto p-3 text-xs leading-5 text-white/62">{JSON.stringify(value, null, 2)}</pre>
    </div>
  );
}

function ActionPanel({ action }: { action: ProposedAction }) {
  const parameters = action.parameters || {};
  const summary = actionSummary(action.action_type, parameters);
  const detailRows = actionDetails(parameters);

  return (
    <div className="rounded-md border border-emerald-200/20 bg-emerald-200/[0.06]">
      <div className="border-b border-emerald-200/15 px-4 py-3">
        <p className="text-xs font-semibold uppercase tracking-[0.22em] text-emerald-100/55">
          Proposed action
        </p>
        <h3 className="mt-2 text-lg font-semibold text-white">{summary.title}</h3>
      </div>
      <div className="grid gap-4 p-4">
        <p className="text-sm leading-6 text-white/72">{summary.body}</p>
        {detailRows.length ? (
          <div className="grid gap-2">
            {detailRows.map(([label, value]) => (
              <div
                key={label}
                className="grid gap-1 rounded-md border border-white/10 bg-black/20 px-3 py-2 sm:grid-cols-[140px_1fr]"
              >
                <span className="text-xs font-semibold uppercase tracking-[0.18em] text-white/35">
                  {label}
                </span>
                <span className="break-words text-sm font-medium text-white/78">{value}</span>
              </div>
            ))}
          </div>
        ) : null}
        {action.rationale_short || action.rationale ? (
          <p className="border-t border-white/10 pt-3 text-sm leading-6 text-white/55">
            {String(action.rationale_short || action.rationale)}
          </p>
        ) : null}
      </div>
    </div>
  );
}

function actionSummary(actionType: string | undefined, parameters: Record<string, unknown>) {
  switch (actionType) {
    case "require_prepaid_for_segment":
      return {
        title: "Require prepaid for this segment",
        body: `Apply a prepaid-only rule to ${segmentText(parameters)} before accepting new COD orders.`,
      };
    case "switch_default_courier_for_route":
      return {
        title: "Switch the default courier for this route",
        body: `Review courier assignment on ${valueText(parameters.route, "this route")} and move future shipments away from the underperforming courier.`,
      };
    case "escalate_to_courier_support":
      return {
        title: "Escalate this shipment to courier support",
        body: `Open a support escalation for ${valueText(parameters.awb_code, "this AWB")} with ${valueText(parameters.courier_name, "the courier")}.`,
      };
    case "review_refund_policy_for_shipped_orders":
      return {
        title: "Review refund handling for shipped orders",
        body: "Check whether this refund should trigger a shipping-cost recovery workflow or a policy exception.",
      };
    case "notify_customer_proactively":
      return {
        title: "Notify the customer proactively",
        body: `Send a delivery-delay update for ${valueText(parameters.awb_code, "this shipment")} before the customer follows up.`,
      };
    default:
      return {
        title: titleize(actionType || "review finding"),
        body: "Review this finding and apply the recommended operational change.",
      };
  }
}

function actionDetails(parameters: Record<string, unknown>): Array<[string, string]> {
  return Object.entries(parameters)
    .filter(([, value]) => value !== null && value !== undefined && value !== "")
    .map(([key, value]) => [titleize(key), formatParameter(value)]);
}

function segmentText(parameters: Record<string, unknown>) {
  const payment = valueText(parameters.payment_method, "selected payment methods").toUpperCase();
  const pincode = valueText(parameters.pincode_prefix, "");
  return pincode ? `${payment} orders where pincode starts with ${pincode}` : `${payment} orders`;
}

function valueText(value: unknown, fallback: string) {
  if (value === null || value === undefined || value === "") return fallback;
  return String(value);
}

function formatParameter(value: unknown): string {
  if (Array.isArray(value)) return value.map((item) => formatParameter(item)).join(", ");
  if (typeof value === "object" && value !== null) {
    return Object.entries(value as Record<string, unknown>)
      .map(([key, nested]) => `${titleize(key)}: ${formatParameter(nested)}`)
      .join("; ");
  }
  return String(value);
}

function severityClass(severity: string) {
  if (severity === "high") return "bg-rose-300/15 text-rose-100 ring-1 ring-rose-200/20";
  if (severity === "medium") return "bg-amber-300/15 text-amber-100 ring-1 ring-amber-200/20";
  return "bg-white/10 text-white/70 ring-1 ring-white/10";
}

function titleize(value: string) {
  return value.replaceAll("_", " ");
}

function money(value: number | null) {
  return value === null || value === 0 ? "Rs 0" : `Rs ${value.toLocaleString("en-IN")}`;
}

function latestRunLabel(run: AgentRun) {
  const timestamp = run.finished_at || run.created_at;
  if (!timestamp) return `Latest saved run: ${run.findings_count} findings`;
  return `Latest saved run: ${run.findings_count} findings, ${new Date(timestamp).toLocaleString()}`;
}
