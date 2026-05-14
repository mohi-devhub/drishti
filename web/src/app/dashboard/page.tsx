"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { AppHeader, apiBase, authHeaders, labels, useDemoAuth } from "../components";

type Finding = {
  id: string;
  duty: string;
  finding_type: string;
  severity: string;
  confidence: number;
  evidence_row_ids: string[];
  estimated_saving_inr_low: number | null;
  estimated_saving_inr_high: number | null;
  narrative_status: string;
  created_at: string;
};

const quickQuestions = [
  "What's my total revenue this month?",
  "Which courier lanes are hurting margin?",
  "Where is RTO risk concentrated?",
];

export default function DashboardPage() {
  const auth = useDemoAuth();
  const [findings, setFindings] = useState<Finding[]>([]);
  const [status, setStatus] = useState("Ready");
  const [busy, setBusy] = useState(false);

  const loadFindings = useCallback(async () => {
    if (!auth.token) return;
    try {
      const response = await fetch(`${apiBase()}/api/findings`, { headers: authHeaders(auth.token) });
      const payload = await response.json();
      if (!response.ok) throw new Error(JSON.stringify(payload));
      setFindings(payload.findings || []);
      setStatus("Synced");
    } catch (error) {
      setStatus("API unavailable");
      console.error(error);
    }
  }, [auth.token]);

  async function runAgent() {
    if (!auth.token) return;
    setBusy(true);
    setStatus("Running");
    try {
      const response = await fetch(`${apiBase()}/agents/rto_shipping_margin/runs`, {
        method: "POST",
        headers: authHeaders(auth.token),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(JSON.stringify(payload));
      setStatus(`${payload.findings_count} findings`);
      setBusy(false);
      void loadFindings();
    } catch (error) {
      setStatus("Failed");
      console.error(error);
      setBusy(false);
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void loadFindings();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [loadFindings]);

  const summary = useMemo(() => {
    const high = findings.filter((finding) => finding.severity === "high").length;
    const savingsLow = findings.reduce((total, finding) => total + (finding.estimated_saving_inr_low || 0), 0);
    const savingsHigh = findings.reduce((total, finding) => total + (finding.estimated_saving_inr_high || 0), 0);
    const evidenceRows = findings.reduce((total, finding) => total + finding.evidence_row_ids.length, 0);
    return { high, savingsLow, savingsHigh, evidenceRows };
  }, [findings]);

  return (
    <main className="min-h-screen text-white">
      <AppHeader
        merchant={auth.merchant}
        token={auth.token}
        error={auth.error}
        onMerchant={auth.refresh}
      />

      <section className="mx-auto grid max-w-7xl gap-5 px-5 py-8">
        <div className="grid gap-5 lg:grid-cols-[0.95fr_1.05fr]">
          <section className="rounded-lg border border-white/10 bg-white/[0.035] p-6 shadow-2xl shadow-black/40">
            <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
              <div>
                <p className="text-xs font-medium uppercase tracking-[0.28em] text-white/35">{labels[auth.merchant]}</p>
                <h1 className="mt-2 text-4xl font-semibold tracking-[-0.05em] text-white">Ops dashboard</h1>
              </div>
              <button
                onClick={runAgent}
                disabled={busy || !auth.token}
                className={`flex h-11 items-center justify-center rounded-full border px-5 text-sm font-semibold leading-none transition disabled:cursor-not-allowed ${
                  busy
                    ? "border-emerald-200/35 bg-emerald-200/15 text-emerald-50"
                    : "border-white/15 bg-white/[0.04] text-white hover:border-emerald-200/50 hover:bg-emerald-200/10"
                }`}
              >
                {busy ? "Running agent" : "Run agent"}
              </button>
            </div>
            <div className="mt-6 grid gap-3 sm:grid-cols-3">
              <MiniStat label="Status" value={status} />
              <MiniStat label="Evidence" value={`${summary.evidenceRows} rows`} />
              <MiniStat label="Agent" value={busy ? "Running" : "Idle"} />
            </div>
          </section>

          <section className="relative overflow-hidden rounded-lg border border-white/10 bg-[#080c0a]/80 p-6 shadow-2xl shadow-black/40">
            <div className="absolute inset-0 opacity-55 [background-image:radial-gradient(rgba(255,255,255,0.16)_1px,transparent_1px)] [background-size:18px_18px]" />
            <div className="relative grid gap-3 sm:grid-cols-2">
              <MetricCard label="Open findings" value={String(findings.length)} accent="white" />
              <MetricCard label="High severity" value={String(summary.high)} accent="rose" />
              <MetricCard label="Savings low" value={money(summary.savingsLow)} accent="emerald" />
              <MetricCard label="Savings high" value={money(summary.savingsHigh)} accent="amber" />
            </div>
          </section>
        </div>

        <section className="rounded-lg border border-white/10 bg-white/[0.035] p-5 shadow-2xl shadow-black/30">
          <div className="flex items-center justify-between border-b border-white/10 pb-4">
            <div>
              <p className="text-xs font-medium uppercase tracking-[0.24em] text-white/35">Demo pipeline</p>
              <h2 className="mt-2 text-xl font-semibold tracking-[-0.03em] text-white">Source health</h2>
            </div>
            <span className="rounded-full border border-emerald-200/20 bg-emerald-200/10 px-3 py-1 text-xs font-medium text-emerald-100">
              {status}
            </span>
          </div>
          <div className="mt-4 grid gap-3">
            <PipelineRow label="Orders" value="Revenue, refunds, COD state" count={summary.evidenceRows || 0} />
            <PipelineRow label="Shipments" value="Courier charge, RTO, delivery lane" count={findings.length} />
            <PipelineRow label="Narratives" value="Cited summaries and proposed actions" count={summary.high} />
          </div>
        </section>

        <div className="grid gap-5 lg:grid-cols-[1fr_0.82fr]">
          <section className="rounded-lg border border-white/10 bg-white/[0.035] shadow-2xl shadow-black/30">
            <div className="flex items-center justify-between border-b border-white/10 px-5 py-4">
              <h2 className="text-sm font-semibold text-white">Live finding queue</h2>
              <Link className="text-sm font-medium text-emerald-200 hover:text-white" href="/findings">
                Open findings
              </Link>
            </div>
            <div className="divide-y divide-white/10">
              {findings.slice(0, 5).map((finding) => (
                <Link key={finding.id} href="/findings" className="grid gap-3 px-5 py-4 transition hover:bg-white/[0.04] md:grid-cols-[1fr_auto]">
                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${severityClass(finding.severity)}`}>
                        {finding.severity}
                      </span>
                      <span className="text-xs font-medium uppercase tracking-[0.22em] text-white/35">{finding.duty}</span>
                    </div>
                    <p className="mt-2 text-sm font-semibold text-white">{titleize(finding.finding_type)}</p>
                  </div>
                  <div className="text-left md:text-right">
                    <p className="text-sm font-semibold text-white">
                      {money(finding.estimated_saving_inr_low)} - {money(finding.estimated_saving_inr_high)}
                    </p>
                    <p className="mt-1 text-xs text-white/40">{finding.evidence_row_ids.length} rows</p>
                  </div>
                </Link>
              ))}
              {findings.length === 0 ? (
                <div className="px-5 py-12 text-center text-sm text-white/45">No findings loaded for this merchant.</div>
              ) : null}
            </div>
          </section>

          <section className="rounded-lg border border-white/10 bg-white/[0.035] shadow-2xl shadow-black/30">
            <div className="border-b border-white/10 px-5 py-4">
              <h2 className="text-sm font-semibold text-white">Question shortcuts</h2>
            </div>
            <div className="grid gap-3 p-5">
              {quickQuestions.map((question) => (
                <Link
                  key={question}
                  href={`/chat?q=${encodeURIComponent(question)}`}
                  className="group rounded-md border border-white/10 bg-black/25 px-4 py-4 text-sm font-medium text-white/78 transition hover:border-emerald-200/40 hover:bg-emerald-200/10 hover:text-white"
                >
                  <span className="mr-3 text-emerald-200">+</span>
                  {question}
                </Link>
              ))}
            </div>
          </section>
        </div>
      </section>
    </main>
  );
}

function MiniStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-white/10 bg-black/20 p-3">
      <p className="text-xs font-medium uppercase tracking-[0.22em] text-white/35">{label}</p>
      <p className="mt-2 truncate text-sm font-semibold text-white">{value}</p>
    </div>
  );
}

function MetricCard({ label, value, accent }: { label: string; value: string; accent: "white" | "rose" | "emerald" | "amber" }) {
  const accentClass = {
    white: "text-white",
    rose: "text-rose-200",
    emerald: "text-emerald-200",
    amber: "text-amber-200",
  }[accent];
  return (
    <div className="rounded-md border border-white/10 bg-white/[0.055] p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.06)]">
      <p className="text-xs font-medium uppercase tracking-[0.22em] text-white/35">{label}</p>
      <p className={`mt-3 min-h-9 text-2xl font-semibold tracking-[-0.03em] ${accentClass}`}>{value}</p>
    </div>
  );
}

function PipelineRow({ label, value, count }: { label: string; value: string; count: number }) {
  return (
    <div className="grid gap-3 rounded-md border border-white/10 bg-white/[0.045] p-3 sm:grid-cols-[120px_1fr_auto] sm:items-center">
      <div className="flex items-center gap-2">
        <span className="size-2 rounded-full bg-emerald-300 shadow-[0_0_14px_rgba(110,231,183,0.8)]" />
        <span className="text-sm font-semibold text-white">{label}</span>
      </div>
      <p className="text-sm text-white/48">{value}</p>
      <span className="rounded-full bg-white/10 px-2 py-1 text-xs font-medium text-white/65">{count}</span>
    </div>
  );
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
