"use client";

import {
  ActivitySquare,
  AlertTriangle,
  ArrowUpRight,
  PlayCircle,
  Receipt,
  ShieldAlert,
  Sparkles,
  TrendingUp,
} from "lucide-react";
import Link from "next/link";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import {
  AppHeader,
  SkeletonLine,
  apiBase,
  authHeaders,
  labels,
  moneyRange,
  titleize,
  useDemoAuth,
} from "../components";

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

type AgentRun = {
  id?: string;
  trigger?: string;
  status?: string;
  findings_count?: number;
  finished_at?: string | null;
  created_at?: string | null;
};

type AgentRunResponse = {
  run_id: string;
  status: string;
  findings_count: number;
};

const quickQuestions = [
  "What's my total revenue this month?",
  "Which courier lanes are hurting margin?",
  "Where is RTO risk concentrated?",
];

export default function DashboardPage() {
  const auth = useDemoAuth();
  const [findings, setFindings] = useState<Finding[]>([]);
  const [run, setRun] = useState<AgentRun | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [apiError, setApiError] = useState(false);
  const [composer, setComposer] = useState("");

  const loadFindings = useCallback(async (): Promise<boolean> => {
    if (!auth.token) return false;
    setLoading(true);
    try {
      const response = await fetch(`${apiBase()}/api/findings`, {
        headers: authHeaders(auth.token),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(JSON.stringify(payload));
      setFindings(payload.findings || []);
      setRun(payload.run || null);
      setApiError(false);
      return true;
    } catch (error) {
      console.error(error);
      setApiError(true);
      return false;
    } finally {
      setLoading(false);
    }
  }, [auth.token]);

  async function runAgent() {
    if (!auth.token) return;
    setBusy(true);
    try {
      const response = await fetch(
        `${apiBase()}/agents/rto_shipping_margin/runs`,
        {
          method: "POST",
          headers: authHeaders(auth.token),
        },
      );
      const payload = await response.json();
      if (!response.ok) throw new Error(JSON.stringify(payload));
      await pollAgentRun(payload.run_id);
      await loadFindings();
    } catch (error) {
      console.error(error);
      await loadFindings();
    } finally {
      setBusy(false);
    }
  }

  async function pollAgentRun(runId: string): Promise<AgentRunResponse> {
    for (let attempt = 0; attempt < 60; attempt += 1) {
      const response = await fetch(
        `${apiBase()}/agents/rto_shipping_margin/runs/${runId}`,
        { headers: authHeaders(auth.token) },
      );
      const payload = await response.json();
      if (!response.ok) throw new Error(JSON.stringify(payload));
      if (!["queued", "running"].includes(payload.status)) return payload;
      await new Promise((resolve) => window.setTimeout(resolve, 1500));
    }
    throw new Error("Agent run timed out");
  }

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void loadFindings();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [loadFindings]);

  const summary = useMemo(() => {
    const counts = { high: 0, medium: 0, low: 0 };
    const byDuty: Record<string, number> = {};
    let savingsLow = 0;
    let savingsHigh = 0;
    let evidenceRows = 0;

    for (const finding of findings) {
      if (finding.severity === "high") counts.high += 1;
      else if (finding.severity === "medium") counts.medium += 1;
      else counts.low += 1;
      byDuty[finding.duty] = (byDuty[finding.duty] || 0) + 1;
      if (typeof finding.estimated_saving_inr_low === "number") {
        savingsLow += finding.estimated_saving_inr_low;
      }
      if (typeof finding.estimated_saving_inr_high === "number") {
        savingsHigh += finding.estimated_saving_inr_high;
      }
      evidenceRows += finding.evidence_row_ids.length;
    }

    const totalCounts = counts.high + counts.medium + counts.low;
    const byDutyList = Object.entries(byDuty)
      .map(([duty, count]) => ({ duty, count }))
      .sort((a, b) => b.count - a.count);
    const maxDutyCount = byDutyList[0]?.count || 1;

    return {
      counts,
      total: totalCounts,
      byDutyList,
      maxDutyCount,
      savingsLow: findings.length ? savingsLow : null,
      savingsHigh: findings.length ? savingsHigh : null,
      evidenceRows,
    };
  }, [findings]);

  const topFindings = useMemo(() => {
    return [...findings]
      .sort((a, b) => {
        const order = { high: 0, medium: 1, low: 2 } as Record<string, number>;
        const sa = order[a.severity] ?? 3;
        const sb = order[b.severity] ?? 3;
        if (sa !== sb) return sa - sb;
        return (b.estimated_saving_inr_high ?? 0) - (a.estimated_saving_inr_high ?? 0);
      })
      .slice(0, 5);
  }, [findings]);

  function submitComposer(event: FormEvent) {
    event.preventDefault();
    const trimmed = composer.trim();
    if (!trimmed) return;
    window.location.href = `/chat?q=${encodeURIComponent(trimmed)}`;
  }

  return (
    <main className="min-h-screen text-white">
      <AppHeader
        merchant={auth.merchant}
        token={auth.token}
        error={auth.error}
        authMode={auth.authMode}
        onMerchant={auth.refresh}
      />
      <section className="mx-auto max-w-7xl gap-5 px-5 py-8">
        <HeroStrip
          merchantLabel={labels[auth.merchant]}
          run={run}
          busy={busy}
          loading={loading}
          apiError={apiError}
          onRunAgent={runAgent}
        />

        <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <KpiCard
            icon={ActivitySquare}
            label="Open findings"
            value={loading ? null : apiError ? "—" : String(summary.total)}
            hint={apiError ? "Could not load" : summary.total === 0 ? "No active findings" : `${summary.counts.high} high · ${summary.counts.medium} med`}
          />
          <KpiCard
            icon={ShieldAlert}
            label="High severity"
            value={loading ? null : apiError ? "—" : String(summary.counts.high)}
            hint={apiError ? "Could not load" : summary.counts.high === 0 ? "Nothing urgent" : "Needs review"}
            tone={!apiError && summary.counts.high > 0 ? "danger" : "neutral"}
          />
          <KpiCard
            icon={TrendingUp}
            label="Potential savings"
            value={loading ? null : apiError ? "—" : moneyRange(summary.savingsLow, summary.savingsHigh)}
            hint={apiError ? "Could not load" : "Cited across findings"}
          />
          <KpiCard
            icon={Receipt}
            label="Evidence rows"
            value={loading ? null : apiError ? "—" : String(summary.evidenceRows)}
            hint={apiError ? "Could not load" : "Cross-tool joins"}
          />
        </div>

        <div className="mt-5 grid gap-5 lg:grid-cols-[1fr_1.2fr]">
          <Card title="Severity breakdown" subtitle="Distribution of open findings">
            {loading ? (
              <SeverityBreakdownSkeleton />
            ) : apiError ? (
              <EmptyState
                icon={AlertTriangle}
                title="Couldn't load findings"
                body="The backend didn't respond. Check that the API is reachable."
              />
            ) : summary.total === 0 ? (
              <EmptyState
                icon={Sparkles}
                title="No findings yet"
                body="Run the agent to surface RTO risk, freight drift, and refund mismatches."
              />
            ) : (
              <SeverityBreakdown counts={summary.counts} total={summary.total} />
            )}
          </Card>

          <Card
            title="Top findings"
            subtitle="Highest impact, ranked by severity and savings"
            action={
              <Link
                href="/findings"
                className="inline-flex items-center gap-1 text-sm font-medium text-emerald-300 hover:text-emerald-200"
              >
                Open all
                <ArrowUpRight className="size-3.5" strokeWidth={2.25} />
              </Link>
            }
          >
            {loading ? (
              <FindingListSkeleton />
            ) : apiError ? (
              <EmptyState
                icon={AlertTriangle}
                title="Couldn't load findings"
                body="The backend didn't respond. Check that the API is reachable."
              />
            ) : topFindings.length === 0 ? (
              <EmptyState
                icon={Sparkles}
                title="Nothing to flag"
                body="When the agent finds something worth your time, it will appear here."
              />
            ) : (
              <ul className="divide-y divide-white/5">
                {topFindings.map((finding) => (
                  <li key={finding.id}>
                    <Link
                      href="/findings"
                      className="grid gap-2 px-1 py-3 transition-colors hover:bg-white/[0.03] sm:grid-cols-[1fr_auto] sm:items-center"
                    >
                      <div>
                        <div className="flex flex-wrap items-center gap-2">
                          <SeverityBadge severity={finding.severity} />
                          <span className="text-xs font-medium uppercase tracking-[0.22em] text-white/40">
                            {finding.duty}
                          </span>
                        </div>
                        <p className="mt-2 text-sm font-semibold text-white">
                          {titleize(finding.finding_type)}
                        </p>
                      </div>
                      <div className="sm:text-right">
                        <p className="text-sm font-semibold text-white">
                          {moneyRange(
                            finding.estimated_saving_inr_low,
                            finding.estimated_saving_inr_high,
                          )}
                        </p>
                        <p className="mt-1 text-xs text-white/45">
                          {finding.evidence_row_ids.length} cited rows
                        </p>
                      </div>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>

        <div className="mt-5 grid gap-5 lg:grid-cols-[1.2fr_1fr]">
          <Card title="Findings by duty" subtitle="Where the agent is finding most signal">
            {loading ? (
              <DutyBreakdownSkeleton />
            ) : apiError ? (
              <EmptyState
                icon={AlertTriangle}
                title="Couldn't load findings"
                body="The backend didn't respond. Check that the API is reachable."
              />
            ) : summary.byDutyList.length === 0 ? (
              <EmptyState
                icon={ActivitySquare}
                title="The agent hasn't run yet"
                body="Once it does, you'll see which duties are pulling the most weight."
              />
            ) : (
              <DutyBreakdown
                items={summary.byDutyList}
                maxCount={summary.maxDutyCount}
              />
            )}
          </Card>

          <Card title="Agent activity" subtitle="When Drishti last looked at your data">
            <ActivityCard run={run} loading={loading} apiError={apiError} />
          </Card>
        </div>

        <Card
          className="mt-5"
          title="Ask Drishti"
          subtitle="Cross-tool question? Type it and we'll cite every answer."
        >
          <form onSubmit={submitComposer} className="grid gap-3 sm:grid-cols-[1fr_auto]">
            <input
              value={composer}
              onChange={(event) => setComposer(event.target.value)}
              placeholder="e.g. Which pincodes drove the most RTO loss this month?"
              className="h-12 rounded-full border border-white/10 bg-black/30 px-5 text-sm font-medium text-white outline-none transition placeholder:text-white/30 focus:border-emerald-200/40 focus:bg-black/40"
            />
            <button
              type="submit"
              disabled={!composer.trim()}
              className="inline-flex h-12 items-center justify-center gap-2 rounded-full bg-white px-6 text-sm font-semibold text-black transition hover:bg-emerald-100 disabled:cursor-not-allowed disabled:bg-white/40"
            >
              Ask
              <ArrowUpRight className="size-4" strokeWidth={2.25} />
            </button>
          </form>
          <div className="mt-4 flex flex-wrap gap-2">
            {quickQuestions.map((question) => (
              <button
                key={question}
                type="button"
                onClick={() => setComposer(question)}
                className="rounded-full border border-white/10 bg-white/[0.04] px-3 py-1.5 text-xs font-medium text-white/70 transition hover:border-emerald-200/40 hover:bg-emerald-200/10 hover:text-white"
              >
                {question}
              </button>
            ))}
          </div>
        </Card>
      </section>
    </main>
  );
}

function HeroStrip({
  merchantLabel,
  run,
  busy,
  loading,
  apiError,
  onRunAgent,
}: {
  merchantLabel: string;
  run: AgentRun | null;
  busy: boolean;
  loading: boolean;
  apiError: boolean;
  onRunAgent: () => void;
}) {
  return (
    <section
      className="relative overflow-hidden rounded-2xl border border-white/10 bg-white/[0.025] p-6 shadow-2xl shadow-black/40 sm:p-8"
      style={{
        backgroundImage:
          "radial-gradient(circle at 0% 0%, rgba(110,231,183,0.08), transparent 50%), radial-gradient(circle at 100% 100%, rgba(110,231,183,0.05), transparent 60%)",
      }}
    >
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.28em] text-white/45">
            {merchantLabel}
          </p>
          <h1 className="mt-2 text-3xl font-semibold tracking-[-0.04em] sm:text-4xl">
            Operations
          </h1>
          <p className="mt-2 max-w-md text-sm leading-6 text-white/55">
            What changed across your tools and what needs attention right now.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <AgentStatusBadge run={run} loading={loading} apiError={apiError} busy={busy} />
          <button
            onClick={onRunAgent}
            disabled={busy || loading}
            className="inline-flex h-11 items-center gap-2 rounded-full bg-white px-5 text-sm font-semibold text-black transition hover:bg-emerald-100 disabled:cursor-not-allowed disabled:bg-white/50"
          >
            <PlayCircle className="size-4" strokeWidth={2.25} />
            {busy ? "Running…" : run ? "Run again" : "Run agent"}
          </button>
        </div>
      </div>
    </section>
  );
}

function AgentStatusBadge({
  run,
  loading,
  apiError,
  busy,
}: {
  run: AgentRun | null;
  loading: boolean;
  apiError: boolean;
  busy: boolean;
}) {
  if (loading && !run) {
    return (
      <span className="inline-flex h-11 items-center gap-2 rounded-full border border-white/10 bg-black/25 px-4 text-xs font-medium text-white/55">
        <span className="size-2 animate-pulse rounded-full bg-white/40" />
        Loading
      </span>
    );
  }
  if (apiError) {
    return (
      <span className="inline-flex h-11 items-center gap-2 rounded-full border border-rose-300/30 bg-rose-300/10 px-4 text-xs font-medium text-rose-100">
        <span className="size-2 rounded-full bg-rose-300" />
        API unavailable
      </span>
    );
  }
  if (busy) {
    return (
      <span className="inline-flex h-11 items-center gap-2 rounded-full border border-emerald-300/30 bg-emerald-300/10 px-4 text-xs font-medium text-emerald-100">
        <span className="size-2 animate-pulse rounded-full bg-emerald-300" />
        Agent running
      </span>
    );
  }
  if (!run) {
    return (
      <span className="inline-flex h-11 items-center gap-2 rounded-full border border-white/10 bg-black/25 px-4 text-xs font-medium text-white/55">
        <span className="size-2 rounded-full bg-white/40" />
        Idle
      </span>
    );
  }
  const timeAgo = run.finished_at || run.created_at;
  return (
    <span className="inline-flex h-11 items-center gap-2 rounded-full border border-emerald-300/25 bg-emerald-300/10 px-4 text-xs font-medium text-emerald-100">
      <span className="size-2 rounded-full bg-emerald-300" />
      Last run {timeAgo ? formatRelative(timeAgo) : "recently"}
    </span>
  );
}

function KpiCard({
  icon: Icon,
  label,
  value,
  hint,
  tone = "neutral",
}: {
  icon: typeof TrendingUp;
  label: string;
  value: string | null;
  hint: string;
  tone?: "neutral" | "danger";
}) {
  const accent = tone === "danger" ? "text-rose-200" : "text-white";
  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.025] p-5 shadow-2xl shadow-black/40 transition hover:border-white/15 hover:bg-white/[0.04]">
      <div className="flex items-center justify-between">
        <p className="text-xs font-semibold uppercase tracking-[0.22em] text-white/45">
          {label}
        </p>
        <Icon className="size-4 text-white/40" strokeWidth={2} />
      </div>
      {value === null ? (
        <SkeletonLine className="mt-4 h-8 w-24" />
      ) : (
        <p className={`mt-4 text-3xl font-semibold tracking-[-0.03em] ${accent}`}>
          {value}
        </p>
      )}
      <p className="mt-2 text-xs text-white/45">{hint}</p>
    </div>
  );
}

function Card({
  title,
  subtitle,
  action,
  className,
  children,
}: {
  title: string;
  subtitle?: string;
  action?: React.ReactNode;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <section
      className={`rounded-2xl border border-white/10 bg-white/[0.025] p-5 shadow-2xl shadow-black/40 sm:p-6 ${className || ""}`}
    >
      <header className="flex flex-wrap items-start justify-between gap-3 pb-4">
        <div>
          <h2 className="text-base font-semibold text-white">{title}</h2>
          {subtitle ? (
            <p className="mt-1 text-xs text-white/45">{subtitle}</p>
          ) : null}
        </div>
        {action}
      </header>
      <div>{children}</div>
    </section>
  );
}

function SeverityBreakdown({
  counts,
  total,
}: {
  counts: { high: number; medium: number; low: number };
  total: number;
}) {
  const items: Array<{
    label: "high" | "medium" | "low";
    value: number;
    bar: string;
    text: string;
  }> = [
    { label: "high", value: counts.high, bar: "bg-rose-300", text: "text-rose-200" },
    { label: "medium", value: counts.medium, bar: "bg-amber-300", text: "text-amber-200" },
    { label: "low", value: counts.low, bar: "bg-emerald-300", text: "text-emerald-100" },
  ];
  return (
    <div className="grid gap-4">
      {items.map((item) => {
        const percent = total ? Math.round((item.value / total) * 100) : 0;
        return (
          <div key={item.label} className="grid gap-2">
            <div className="flex items-center justify-between text-sm">
              <span className={`font-semibold capitalize ${item.text}`}>
                {item.label}
              </span>
              <span className="font-mono text-white/55">
                {item.value}
                <span className="ml-2 text-white/30">{percent}%</span>
              </span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-white/[0.06]">
              <div
                className={`h-full rounded-full transition-all duration-500 ${item.bar}`}
                style={{ width: `${percent}%` }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}

function DutyBreakdown({
  items,
  maxCount,
}: {
  items: Array<{ duty: string; count: number }>;
  maxCount: number;
}) {
  return (
    <div className="grid gap-3">
      {items.map((item) => {
        const percent = maxCount ? (item.count / maxCount) * 100 : 0;
        return (
          <div key={item.duty} className="grid gap-2">
            <div className="flex items-center justify-between text-sm">
              <span className="font-medium text-white">{titleize(item.duty)}</span>
              <span className="font-mono text-xs text-white/55">{item.count}</span>
            </div>
            <div className="h-1.5 overflow-hidden rounded-full bg-white/[0.06]">
              <div
                className="h-full rounded-full bg-gradient-to-r from-emerald-300/80 to-emerald-200/40 transition-all duration-500"
                style={{ width: `${percent}%` }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}

function ActivityCard({
  run,
  loading,
  apiError,
}: {
  run: AgentRun | null;
  loading: boolean;
  apiError: boolean;
}) {
  if (loading) {
    return (
      <div className="grid gap-3">
        <SkeletonLine className="h-4 w-3/4" />
        <SkeletonLine className="h-4 w-1/2" />
        <SkeletonLine className="h-4 w-2/3" />
      </div>
    );
  }
  if (apiError) {
    return (
      <EmptyState
        icon={AlertTriangle}
        title="API unavailable"
        body="Couldn't reach the backend for activity data."
      />
    );
  }
  if (!run) {
    return (
      <EmptyState
        icon={ActivitySquare}
        title="No runs yet"
        body="When you trigger the agent, the run summary will appear here."
      />
    );
  }
  const finishedAt = run.finished_at;
  return (
    <dl className="grid gap-4 text-sm">
      <Row
        label="Status"
        value={
          <span className="inline-flex items-center gap-2 font-semibold">
            <span
              className={`size-2 rounded-full ${
                run.status === "completed"
                  ? "bg-emerald-300"
                  : run.status === "partial"
                    ? "bg-amber-300"
                    : "bg-white/40"
              }`}
            />
            {titleize(run.status || "unknown")}
          </span>
        }
      />
      <Row
        label="Findings"
        value={
          <span className="font-mono text-white">{run.findings_count ?? 0}</span>
        }
      />
      <Row
        label="Trigger"
        value={
          <span className="text-white/75">{titleize(run.trigger || "manual")}</span>
        }
      />
      <Row
        label="Finished"
        value={
          <span className="text-white/75">
            {finishedAt ? formatRelative(finishedAt) : "—"}
          </span>
        }
      />
    </dl>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between border-b border-white/5 pb-3 last:border-0 last:pb-0">
      <dt className="text-xs font-medium uppercase tracking-[0.2em] text-white/40">
        {label}
      </dt>
      <dd>{value}</dd>
    </div>
  );
}

function EmptyState({
  icon: Icon,
  title,
  body,
}: {
  icon: typeof Sparkles;
  title: string;
  body: string;
}) {
  return (
    <div className="grid place-items-center gap-3 rounded-xl border border-dashed border-white/10 bg-black/15 px-4 py-10 text-center">
      <Icon className="size-5 text-white/50" strokeWidth={1.75} />
      <div>
        <p className="text-sm font-semibold text-white">{title}</p>
        <p className="mt-1 max-w-xs text-xs leading-5 text-white/50">{body}</p>
      </div>
    </div>
  );
}

function SeverityBadge({ severity }: { severity: string }) {
  const styles =
    severity === "high"
      ? "bg-rose-300/15 text-rose-100 ring-rose-200/25"
      : severity === "medium"
        ? "bg-amber-300/15 text-amber-100 ring-amber-200/25"
        : "bg-white/10 text-white/70 ring-white/10";
  return (
    <span
      className={`inline-flex rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.16em] ring-1 ${styles}`}
    >
      {severity}
    </span>
  );
}

function SeverityBreakdownSkeleton() {
  return (
    <div className="grid gap-4">
      {[0, 1, 2].map((index) => (
        <div key={index} className="grid gap-2">
          <div className="flex justify-between">
            <SkeletonLine className="h-4 w-14" />
            <SkeletonLine className="h-4 w-12" />
          </div>
          <SkeletonLine className="h-2 w-full" />
        </div>
      ))}
    </div>
  );
}

function DutyBreakdownSkeleton() {
  return (
    <div className="grid gap-3">
      {[0, 1, 2, 3].map((index) => (
        <div key={index} className="grid gap-2">
          <div className="flex justify-between">
            <SkeletonLine className="h-4 w-32" />
            <SkeletonLine className="h-4 w-8" />
          </div>
          <SkeletonLine className="h-1.5 w-full" />
        </div>
      ))}
    </div>
  );
}

function FindingListSkeleton() {
  return (
    <ul className="divide-y divide-white/5">
      {[0, 1, 2, 3].map((index) => (
        <li key={index} className="grid gap-2 px-1 py-3 sm:grid-cols-[1fr_auto] sm:items-center">
          <div>
            <div className="flex gap-2">
              <SkeletonLine className="h-4 w-16" />
              <SkeletonLine className="h-4 w-24" />
            </div>
            <SkeletonLine className="mt-3 h-4 w-48" />
          </div>
          <div className="sm:text-right">
            <SkeletonLine className="h-4 w-24" />
            <SkeletonLine className="mt-2 h-3 w-20" />
          </div>
        </li>
      ))}
    </ul>
  );
}

function formatRelative(isoTimestamp: string) {
  const ts = new Date(isoTimestamp).getTime();
  if (Number.isNaN(ts)) return "—";
  const diff = Date.now() - ts;
  const sec = Math.round(diff / 1000);
  if (sec < 60) return `${Math.max(0, sec)}s ago`;
  const min = Math.round(sec / 60);
  if (min < 60) return `${min}m ago`;
  const hr = Math.round(min / 60);
  if (hr < 24) return `${hr}h ago`;
  const day = Math.round(hr / 24);
  return `${day}d ago`;
}

