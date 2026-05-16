"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { AppHeader, CitationText, SkeletonLine, apiBase, authHeaders, labels, money, moneyRange, titleize, useDemoAuth } from "../components";
import type { MerchantKey } from "../components";

type Finding = {
  id: string;
  duty: string;
  finding_type: string;
  severity: string;
  lifecycle_status: string;
  fingerprint: string | null;
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

type DutyConfig = {
  duty: string;
  enabled: boolean;
  config: Record<string, unknown>;
  updated_at: string | null;
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
  const [query, setQuery] = useState("");
  const [severity, setSeverity] = useState("all");
  const [lifecycle, setLifecycle] = useState("all");
  const [sort, setSort] = useState("newest");
  const [configs, setConfigs] = useState<DutyConfig[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async (): Promise<boolean> => {
    if (!auth.token) return false;
    setLoading(true);
    try {
      const params = new URLSearchParams({ sort });
      if (severity !== "all") params.set("severity", severity);
      if (lifecycle !== "all") params.set("lifecycle_status", lifecycle);
      if (query.trim()) params.set("q", query.trim());
      const response = await fetch(`${apiBase()}/api/findings?${params.toString()}`, { headers: authHeaders(auth.token) });
      const payload = await response.json();
      if (!response.ok) throw new Error(JSON.stringify(payload));
      setFindings(payload.findings || []);
      setRun(payload.run || null);
      setSelected((current) =>
        current && payload.findings?.some((finding: Finding) => finding.id === current)
          ? current
          : payload.findings?.[0]?.id || null,
      );
      setStatus(payload.run ? latestRunLabel(payload.run) : "Run completed with no findings");
      return true;
    } catch {
      setStatus("API unavailable");
      return false;
    } finally {
      setLoading(false);
    }
  }, [auth.token, lifecycle, query, severity, sort]);

  const loadConfigs = useCallback(async () => {
    if (!auth.token) return;
    const response = await fetch(`${apiBase()}/agents/rto_shipping_margin/duty-configs`, {
      headers: authHeaders(auth.token),
    });
    const payload = await response.json();
    if (response.ok) setConfigs(payload.configs || []);
  }, [auth.token]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void load();
      void loadConfigs();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [load, loadConfigs]);

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

  async function cancelRun() {
    if (!run || !["queued", "running"].includes(run.status)) return;
    setBusy(true);
    try {
      const response = await fetch(`${apiBase()}/agents/rto_shipping_margin/runs/${run.id}/cancel`, {
        method: "POST",
        headers: authHeaders(auth.token),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(JSON.stringify(payload));
      setStatus(`Run ${payload.status}`);
      void load();
    } catch (error) {
      console.error(error);
      setStatus("Cancel failed");
    } finally {
      setBusy(false);
    }
  }

  async function updateLifecycle(findingId: string, lifecycleStatus: string) {
    const response = await fetch(`${apiBase()}/api/findings/${findingId}`, {
      method: "PATCH",
      headers: jsonHeaders(auth.token),
      body: JSON.stringify({ lifecycle_status: lifecycleStatus }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(JSON.stringify(payload));
    setFindings((current) =>
      current.map((finding) => (finding.id === findingId ? { ...finding, ...payload.finding } : finding)),
    );
  }

  async function toggleDuty(duty: string, enabled: boolean) {
    const response = await fetch(`${apiBase()}/agents/rto_shipping_margin/duty-configs/${duty}`, {
      method: "PATCH",
      headers: jsonHeaders(auth.token),
      body: JSON.stringify({ enabled, config: {} }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(JSON.stringify(payload));
    setConfigs((current) => current.map((config) => (config.duty === duty ? payload.config : config)));
  }

  function exportFindings() {
    const blob = new Blob([JSON.stringify({ run, findings }, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `drishti-findings-${auth.merchant}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  async function shareFinding() {
    if (!active) return;
    const url = new URL(window.location.href);
    url.searchParams.set("finding", active.id);
    await navigator.clipboard.writeText(url.toString());
    setStatus("Finding link copied");
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
      setConfigs([]);
      void refresh(merchant);
    },
    [refresh],
  );

  const active = findings.find((finding) => finding.id === selected) || findings[0] || null;
  const summary = useMemo(() => {
    const high = findings.filter((finding) => finding.severity === "high").length;
    const lowValues = findings.map((finding) => finding.estimated_saving_inr_low).filter((value): value is number => value !== null);
    const highValues = findings.map((finding) => finding.estimated_saving_inr_high).filter((value): value is number => value !== null);
    const savingsLow = lowValues.length ? lowValues.reduce((total, value) => total + value, 0) : null;
    const savingsHigh = highValues.length ? highValues.reduce((total, value) => total + value, 0) : null;
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
      <section className="mx-auto max-w-7xl grid gap-5 px-5 py-8">
        <section
          className="relative overflow-hidden rounded-2xl border border-white/10 bg-white/[0.025] p-6 shadow-2xl shadow-black/40 sm:p-8"
          style={{
            backgroundImage:
              "radial-gradient(circle at 0% 0%, rgba(110,231,183,0.08), transparent 50%), radial-gradient(circle at 100% 100%, rgba(110,231,183,0.05), transparent 60%)",
          }}
        >
          <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.28em] text-white/45">{labels[auth.merchant]}</p>
              <h1 className="mt-2 text-3xl font-semibold tracking-[-0.04em] sm:text-4xl">Agent findings</h1>
              <p className="mt-2 max-w-md text-sm leading-6 text-white/55">{status}</p>
            </div>
            <div className="flex flex-wrap items-center gap-3">
              {run && ["queued", "running"].includes(run.status) ? (
                <button
                  onClick={cancelRun}
                  disabled={busy || !auth.token}
                  className="inline-flex h-11 items-center rounded-full border border-rose-300/30 bg-rose-300/10 px-5 text-sm font-semibold text-rose-100 transition hover:bg-rose-300/15 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  Cancel run
                </button>
              ) : null}
              <button
                onClick={exportFindings}
                disabled={!findings.length}
                className="inline-flex h-11 items-center rounded-full border border-white/10 bg-white/[0.04] px-5 text-sm font-semibold text-white/75 transition hover:border-emerald-200/40 hover:bg-emerald-200/10 disabled:cursor-not-allowed disabled:opacity-45"
              >
                Export JSON
              </button>
              <button
                onClick={runAgent}
                disabled={busy || !auth.token}
                className="inline-flex h-11 items-center rounded-full bg-white px-5 text-sm font-semibold text-black transition hover:bg-emerald-100 disabled:cursor-not-allowed disabled:bg-white/40"
              >
                {busy ? "Running…" : run ? "Run again" : "Run agent"}
              </button>
            </div>
          </div>
          <div className="mt-6 grid gap-3 sm:grid-cols-3">
            <Metric label="Total" value={String(findings.length)} loading={loading} />
            <Metric label="High severity" value={String(summary.high)} loading={loading} />
            <Metric label="Savings range" value={moneyRange(summary.savingsLow, summary.savingsHigh)} loading={loading} />
          </div>
        </section>

        <section className="rounded-2xl border border-white/10 bg-white/[0.025] p-5 shadow-2xl shadow-black/40 sm:p-6">
          <div className="grid gap-3 lg:grid-cols-[1fr_160px_170px_150px]">
            <label className="grid gap-1.5">
              <span className="text-[10px] font-semibold uppercase tracking-[0.22em] text-white/45">Search</span>
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Duty, type, narrative…"
                className="h-11 rounded-xl border border-white/10 bg-black/30 px-3.5 text-sm text-white outline-none transition placeholder:text-white/25 focus:border-emerald-200/45 focus:bg-black/40"
              />
            </label>
            <SelectControl label="Severity" value={severity} onChange={setSeverity} options={["all", "high", "medium", "low"]} />
            <SelectControl
              label="Lifecycle"
              value={lifecycle}
              onChange={setLifecycle}
              options={["all", "open", "acknowledged", "actioned", "dismissed"]}
            />
            <SelectControl label="Sort" value={sort} onChange={setSort} options={["newest", "savings", "severity"]} />
          </div>
          {configs.length ? (
            <div className="mt-5 flex flex-wrap items-center gap-2">
              <span className="text-xs font-semibold uppercase tracking-[0.22em] text-white/45">
                Duties
              </span>
              {configs.map((config) => (
                <button
                  key={config.duty}
                  onClick={() => void toggleDuty(config.duty, !config.enabled)}
                  className={`rounded-full border px-3 py-1.5 text-xs font-semibold transition ${
                    config.enabled
                      ? "border-emerald-300/25 bg-emerald-300/10 text-emerald-100"
                      : "border-white/10 bg-black/30 text-white/45 hover:bg-white/[0.05]"
                  }`}
                >
                  {titleize(config.duty)}
                </button>
              ))}
            </div>
          ) : null}
        </section>

        <div className="grid gap-5 xl:grid-cols-[440px_minmax(0,1fr)]">
          <section className="overflow-hidden rounded-2xl border border-white/10 bg-white/[0.025] shadow-2xl shadow-black/40">
            <div className="border-b border-white/10 bg-black/30 px-5 py-4">
              <h2 className="text-sm font-semibold text-white">Finding queue</h2>
              <p className="mt-0.5 text-xs text-white/45">Click a row to inspect</p>
            </div>
            <div className="max-h-[calc(100vh-290px)] min-h-96 overflow-auto p-2">
              {loading ? <FindingListSkeleton /> : null}
              {!loading && findings.map((finding) => (
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
                    <div className="flex flex-wrap items-center gap-2">
                      <span className={`rounded px-2 py-0.5 text-xs font-semibold ${severityClass(finding.severity)}`}>
                        {finding.severity}
                      </span>
                      <span className="rounded bg-white/10 px-2 py-0.5 text-xs font-semibold text-white/55">
                        {finding.lifecycle_status || "open"}
                      </span>
                    </div>
                    <span className="text-xs font-medium text-white/45">{Math.round(finding.confidence * 100)}%</span>
                  </div>
                  <p className="mt-3 text-sm font-semibold text-white">{titleize(finding.finding_type)}</p>
                  <p className="mt-2 text-xs uppercase tracking-[0.22em] text-white/35">{finding.duty}</p>
                  <div className="mt-3 flex items-center justify-between text-xs text-white/50">
                    <span>{finding.evidence_row_ids.length} evidence rows</span>
                    <span>{moneyRange(finding.estimated_saving_inr_low, finding.estimated_saving_inr_high)}</span>
                  </div>
                </button>
              ))}
              {!loading && findings.length === 0 ? (
                <div className="grid min-h-72 place-items-center rounded-md border border-dashed border-white/15 bg-black/20 p-6 text-center text-sm text-white/45">
                  No findings yet for this merchant.
                </div>
              ) : null}
            </div>
          </section>

          <section className="overflow-hidden rounded-2xl border border-white/10 bg-white/[0.025] shadow-2xl shadow-black/40">
            {loading ? (
              <FindingDetailSkeleton />
            ) : active ? (
              <article>
                <div className="border-b border-white/10 bg-black/30 p-5">
                  <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                    <div>
                      <div className="flex flex-wrap items-center gap-2">
                        <span className={`rounded px-2 py-0.5 text-xs font-semibold ${severityClass(active.severity)}`}>
                          {active.severity}
                        </span>
                        <span className="rounded bg-white/10 px-2 py-0.5 text-xs font-semibold text-white/55">
                          {active.lifecycle_status || "open"}
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
                  <div className="mt-4 flex flex-wrap items-center gap-2">
                    {["open", "acknowledged", "actioned", "dismissed"].map((state) => (
                      <button
                        key={state}
                        onClick={() => void updateLifecycle(active.id, state)}
                        className={`rounded-full border px-3 py-1.5 text-xs font-semibold transition ${
                          (active.lifecycle_status || "open") === state
                            ? "border-emerald-200/35 bg-emerald-200/12 text-emerald-50"
                            : "border-white/10 bg-black/20 text-white/55 hover:bg-white/[0.06]"
                        }`}
                      >
                        {state}
                      </button>
                    ))}
                    <button
                      onClick={() => void shareFinding()}
                      className="rounded-full border border-white/10 bg-white/[0.06] px-3 py-1.5 text-xs font-semibold text-white/65 transition hover:border-emerald-200/40 hover:bg-emerald-200/10"
                    >
                      Copy link
                    </button>
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
                  <div className="lg:col-span-2">
                    <ActionPanel action={active.proposed_action as ProposedAction} />
                  </div>
                  <CodePanel title="Evidence row IDs" value={active.evidence_row_ids} />
                  <FingerprintPanel fingerprint={active.fingerprint} />
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

function Metric({ label, value, loading = false }: { label: string; value: string; loading?: boolean }) {
  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.04] p-4">
      <p className="text-xs font-semibold uppercase tracking-[0.22em] text-white/45">{label}</p>
      {loading ? (
        <SkeletonLine className="mt-3 h-8 w-28" />
      ) : (
        <p className="mt-3 min-h-8 text-2xl font-semibold tracking-[-0.02em] text-white">{value}</p>
      )}
    </div>
  );
}

function FindingListSkeleton() {
  return (
    <>
      {[0, 1, 2, 3].map((index) => (
        <div key={index} className="mb-2 rounded-md border border-white/10 bg-black/20 p-3">
          <div className="flex justify-between gap-3">
            <div className="flex gap-2">
              <SkeletonLine className="h-5 w-14" />
              <SkeletonLine className="h-5 w-20" />
            </div>
            <SkeletonLine className="h-4 w-10" />
          </div>
          <SkeletonLine className="mt-3 h-5 w-52" />
          <SkeletonLine className="mt-3 h-4 w-32" />
          <div className="mt-3 flex justify-between gap-3">
            <SkeletonLine className="h-4 w-28" />
            <SkeletonLine className="h-4 w-36" />
          </div>
        </div>
      ))}
    </>
  );
}

function FindingDetailSkeleton() {
  return (
    <div>
      <div className="border-b border-white/10 bg-black/25 p-5">
        <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
          <div>
            <div className="flex gap-2">
              <SkeletonLine className="h-5 w-14" />
              <SkeletonLine className="h-5 w-20" />
              <SkeletonLine className="h-5 w-28" />
            </div>
            <SkeletonLine className="mt-4 h-9 w-72" />
          </div>
          <SkeletonLine className="h-10 w-32" />
        </div>
      </div>
      <div className="grid gap-4 p-5 lg:grid-cols-3">
        <Metric label="Savings low" value="" loading />
        <Metric label="Savings high" value="" loading />
        <Metric label="Evidence rows" value="" loading />
      </div>
      <div className="border-y border-emerald-200/15 bg-emerald-200/10 p-5">
        <SkeletonLine className="h-4 w-full" />
        <SkeletonLine className="mt-3 h-4 w-5/6" />
      </div>
    </div>
  );
}

function SelectControl({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: string[];
}) {
  return (
    <label className="grid gap-1.5">
      <span className="text-[10px] font-semibold uppercase tracking-[0.22em] text-white/45">{label}</span>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="h-11 rounded-xl border border-white/10 bg-black/30 px-3 text-sm text-white outline-none transition focus:border-emerald-200/45 focus:bg-black/40"
      >
        {options.map((option) => (
          <option key={option} value={option} className="bg-black text-white">
            {titleize(option)}
          </option>
        ))}
      </select>
    </label>
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

function FingerprintPanel({ fingerprint }: { fingerprint: string | null }) {
  const short = fingerprint ? `${fingerprint.slice(0, 12)}…` : "Pending";
  return (
    <div className="rounded-md border border-white/10 bg-black/25">
      <div className="border-b border-white/10 px-3 py-2 text-xs font-semibold uppercase tracking-[0.22em] text-white/35">
        Fingerprint
      </div>
      <div className="grid gap-2 p-3">
        <span
          className="font-mono text-sm font-semibold text-white"
          title={fingerprint || "This finding pre-dates the fingerprint feature; re-run the agent to populate."}
        >
          {short}
        </span>
        <span className="text-xs leading-5 text-white/50">
          A stable identity for this finding. Re-detections on later runs share the same fingerprint so we can group history and suppress duplicate alerts.
        </span>
      </div>
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

function latestRunLabel(run: AgentRun) {
  const timestamp = run.finished_at || run.created_at;
  if (!timestamp) return `Latest saved run: ${run.findings_count} findings`;
  return `Latest saved run: ${run.findings_count} findings, ${new Date(timestamp).toLocaleString()}`;
}

function jsonHeaders(token: string): Record<string, string> {
  return { ...authHeaders(token), "content-type": "application/json" };
}
