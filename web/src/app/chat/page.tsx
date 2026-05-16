"use client";

import { Trash2 } from "lucide-react";
import { FormEvent, Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { AppHeader, CitationText, SkeletonLine, apiBase, authHeaders, labels, useDemoAuth, type MerchantKey } from "../components";

type ToolRow = {
  row_id: string;
  raw_record_id: string;
  fetched_from: string;
  values: Record<string, unknown>;
};

type ToolAggregate = {
  agg_id: string;
  label: string;
  value: number;
  unit: string;
  derived_from_row_ids: string[];
  formula: string;
};

type Message = {
  role: "user" | "assistant";
  content: string;
};

type ChatSession = {
  id: string;
  title: string | null;
  message_count: number;
  latest_message: string | null;
  updated_at: string | null;
};

const prompts = [
  "What's my total revenue this month?",
  "Which orders drove the most shipping leakage?",
  "Show the evidence behind the latest RTO finding.",
];

export default function ChatPage() {
  return (
    <Suspense fallback={<main className="min-h-screen bg-[#050706]" />}>
      <ChatWorkspace />
    </Suspense>
  );
}

function ChatWorkspace() {
  const auth = useDemoAuth();
  const { refresh } = auth;
  const params = useSearchParams();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState(params.get("q") || prompts[0]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [rows, setRows] = useState<ToolRow[]>([]);
  const [aggregates, setAggregates] = useState<ToolAggregate[]>([]);
  const [raw, setRaw] = useState<Record<string, unknown> | null>(null);
  const [selectedRowId, setSelectedRowId] = useState<string | null>(null);
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [busy, setBusy] = useState(false);
  const [sessionsLoading, setSessionsLoading] = useState(true);

  useEffect(() => {
    const question = params.get("q");
    if (question) setInput(question);
  }, [params]);

  const loadSessions = useCallback(async () => {
    if (!auth.token) return;
    setSessionsLoading(true);
    try {
      const response = await fetch(`${apiBase()}/chat/sessions`, {
        headers: authHeaders(auth.token),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(JSON.stringify(payload));
      setSessions(payload.sessions || []);
    } catch (error) {
      console.error(error);
    } finally {
      setSessionsLoading(false);
    }
  }, [auth.token]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void loadSessions();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [loadSessions]);

  const switchMerchant = useCallback(
    (merchant: MerchantKey) => {
      setMessages([]);
      setRows([]);
      setAggregates([]);
      setRaw(null);
      setSelectedRowId(null);
      setSessionId(null);
      setSessions([]);
      setSessionsLoading(true);
      setInput(prompts[0]);
      setBusy(false);
      void refresh(merchant);
    },
    [refresh],
  );

  async function send(event: FormEvent) {
    event.preventDefault();
    if (!input.trim() || !auth.token) return;
    const question = input.trim();
    setBusy(true);
    setMessages((current) => [...current, { role: "user", content: question }]);
    setInput("");
    try {
      const streamed = await sendStream(question);
      if (streamed) return;
      const response = await fetch(`${apiBase()}/chat`, {
        method: "POST",
        headers: { "content-type": "application/json", ...authHeaders(auth.token) },
        body: JSON.stringify({ message: question, session_id: sessionId }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(JSON.stringify(payload));
      setSessionId(payload.session_id);
      setMessages((current) => [...current, { role: "assistant", content: payload.answer }]);
      setRows(payload.tool_results.flatMap((result: { rows: ToolRow[] }) => result.rows || []));
      setAggregates(
        payload.tool_results.flatMap((result: { aggregates: ToolAggregate[] }) => result.aggregates || []),
      );
      setRaw(null);
      setSelectedRowId(null);
      void loadSessions();
    } catch (error) {
      setMessages((current) => [...current, { role: "assistant", content: `Request failed: ${String(error)}` }]);
    } finally {
      setBusy(false);
    }
  }

  function newChat() {
    setMessages([]);
    setRows([]);
    setAggregates([]);
    setRaw(null);
    setSelectedRowId(null);
    setSessionId(null);
    setInput(prompts[0]);
  }

  async function deleteSession(id: string) {
    if (!auth.token) return;
    if (!window.confirm("Delete this chat? This cannot be undone.")) return;
    try {
      const token = await auth.getFreshToken();
      const response = await fetch(`${apiBase()}/chat/sessions/${id}`, {
        method: "DELETE",
        headers: authHeaders(token),
      });
      if (!response.ok && response.status !== 204) {
        const text = await response.text();
        throw new Error(text || `Failed to delete (HTTP ${response.status})`);
      }
      setSessions((current) => current.filter((session) => session.id !== id));
      if (sessionId === id) newChat();
    } catch (error) {
      console.error(error);
    }
  }

  async function loadSession(id: string) {
    if (!auth.token) return;
    setBusy(true);
    try {
      const response = await fetch(`${apiBase()}/chat/sessions/${id}`, {
        headers: authHeaders(auth.token),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(JSON.stringify(payload));
      setSessionId(id);
      setMessages(
        (payload.messages || [])
          .filter((message: { role: string }) => message.role === "user" || message.role === "assistant")
          .map((message: { role: "user" | "assistant"; content: string }) => ({
            role: message.role,
            content: message.content,
          })),
      );
      setRows([]);
      setAggregates([]);
      setRaw(null);
      setSelectedRowId(null);
    } catch (error) {
      setMessages((current) => [
        ...current,
        { role: "assistant", content: `Could not load chat: ${String(error)}` },
      ]);
    } finally {
      setBusy(false);
    }
  }

  async function sendStream(question: string) {
    const response = await fetch(`${apiBase()}/chat/stream`, {
      method: "POST",
      headers: { "content-type": "application/json", ...authHeaders(auth.token) },
      body: JSON.stringify({ message: question, session_id: sessionId }),
    });
    if (!response.ok || !response.body) return false;

    const assistantIndex = messages.length + 1;
    setMessages((current) => [...current, { role: "assistant", content: "" }]);

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let finalAnswer = "";
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const frames = buffer.split("\n\n");
      buffer = frames.pop() || "";
      for (const frame of frames) {
        const event = parseSse(frame);
        if (!event) continue;
        if (event.event === "metadata") {
          if (typeof event.data.session_id === "string") setSessionId(event.data.session_id);
          const toolResults = Array.isArray(event.data.tool_results)
            ? (event.data.tool_results as Array<{ rows?: ToolRow[]; aggregates?: ToolAggregate[] }>)
            : [];
          setRows(toolResults.flatMap((result) => result.rows || []));
          setAggregates(toolResults.flatMap((result) => result.aggregates || []));
          setRaw(null);
          setSelectedRowId(null);
        }
        if (event.event === "delta") {
          finalAnswer += typeof event.data.text === "string" ? event.data.text : "";
          setMessages((current) =>
            current.map((message, index) =>
              index === assistantIndex ? { ...message, content: finalAnswer } : message,
            ),
          );
        }
        if (event.event === "done" && typeof event.data.answer === "string") {
          finalAnswer = event.data.answer;
          setMessages((current) =>
            current.map((message, index) =>
              index === assistantIndex ? { ...message, content: finalAnswer } : message,
            ),
          );
        }
      }
    }
    void loadSessions();
    return true;
  }

  async function loadRaw(row: ToolRow) {
    setSelectedRowId(row.row_id);
    setRaw({ status: "loading", row_id: row.row_id });
    if (!row.raw_record_id) {
      setRaw({ row_id: row.row_id, fetched_from: row.fetched_from, values: row.values });
      return;
    }
    try {
      const response = await fetch(`${apiBase()}/api/source_records/${row.raw_record_id}`, {
        headers: authHeaders(auth.token),
      });
      const text = await response.text();
      const payload = text ? JSON.parse(text) : {};
      if (!response.ok) {
        setRaw({
          status: "error",
          row_id: row.row_id,
          raw_record_id: row.raw_record_id,
          detail: payload.detail || payload,
        });
        return;
      }
      setRaw(payload);
    } catch (error) {
      setRaw({
        status: "error",
        row_id: row.row_id,
        raw_record_id: row.raw_record_id,
        detail: String(error),
      });
    }
  }

  function pinCitation(citationId: string) {
    const primaryId = citationId.split(",", 1)[0]?.trim();
    if (!primaryId) return;
    const rowId = primaryId.split("#", 1)[0];
    const row = rows.find((candidate) => candidate.row_id === rowId);
    if (row) {
      void loadRaw(row);
      return;
    }
    const aggregate = aggregates.find((candidate) => candidate.agg_id === primaryId);
    if (!aggregate) return;
    const aggregateRows = rows.filter((candidate) => aggregate.derived_from_row_ids.includes(candidate.row_id));
    setSelectedRowId(aggregate.agg_id);
    setRaw({
      type: "aggregate",
      id: aggregate.agg_id,
      label: aggregate.label,
      value: aggregate.value,
      unit: aggregate.unit,
      formula: aggregate.formula,
      derived_from_row_ids: aggregate.derived_from_row_ids,
      contributing_order_ids: collectContributorIds(aggregateRows, "order"),
      contributing_shipment_ids: collectContributorIds(aggregateRows, "shipment"),
      rows: aggregateRows,
    });
  }

  const lastRows = useMemo(() => rows, [rows]);

  return (
    <main className="min-h-screen text-white">
      <AppHeader
        merchant={auth.merchant}
        token={auth.token}
        error={auth.error}
        authMode={auth.authMode}
        onMerchant={switchMerchant}
      />
      <div className="mx-auto grid max-w-7xl gap-5 px-5 py-8 xl:grid-cols-12">
        <aside className="overflow-hidden rounded-2xl border border-white/10 bg-white/[0.025] shadow-2xl shadow-black/40 xl:col-span-2">
          <div className="border-b border-white/10 bg-black/30 px-4 py-3">
            <h2 className="text-sm font-semibold text-white">Chat history</h2>
          </div>
          <div className="max-h-64 overflow-auto p-2 xl:max-h-[calc(100vh-220px)]">
            {sessionsLoading ? <ChatHistorySkeleton /> : null}
            {!sessionsLoading && sessions.map((chatSession) => (
              <div
                key={chatSession.id}
                className={`group relative mb-2 rounded-xl border transition ${
                  sessionId === chatSession.id
                    ? "border-emerald-300/30 bg-emerald-300/10"
                    : "border-white/10 bg-black/20 hover:bg-white/[0.05]"
                }`}
              >
                <button
                  onClick={() => loadSession(chatSession.id)}
                  className="block w-full px-3 py-3 pr-9 text-left"
                >
                  <span className="block truncate text-sm font-semibold text-white">
                    {chatSession.title || "Untitled chat"}
                  </span>
                  <span className="mt-1 block truncate text-xs text-white/45">
                    {chatSession.latest_message || `${chatSession.message_count} messages`}
                  </span>
                  <span className="mt-1 block text-[10px] font-medium uppercase tracking-[0.18em] text-white/35">
                    {chatSession.updated_at ? formatRelative(chatSession.updated_at) : ""}
                  </span>
                </button>
                <button
                  type="button"
                  aria-label="Delete chat"
                  onClick={(event) => {
                    event.stopPropagation();
                    void deleteSession(chatSession.id);
                  }}
                  className="absolute right-2 top-2 grid size-7 place-items-center rounded-md text-white/45 opacity-0 transition hover:bg-rose-300/15 hover:text-rose-100 focus:opacity-100 group-hover:opacity-100"
                >
                  <Trash2 className="size-3.5" strokeWidth={2} />
                </button>
              </div>
            ))}
            {!sessionsLoading && sessions.length === 0 ? (
              <p className="px-3 py-6 text-center text-xs text-white/45">No saved chats yet</p>
            ) : null}
          </div>
        </aside>

        <section className="flex min-h-[calc(100vh-132px)] flex-col overflow-hidden rounded-2xl border border-white/10 bg-white/[0.025] shadow-2xl shadow-black/40 xl:col-span-6">
          <div
            className="border-b border-white/10 bg-black/30 px-5 py-5"
            style={{
              backgroundImage:
                "radial-gradient(circle at 0% 0%, rgba(110,231,183,0.06), transparent 50%)",
            }}
          >
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.28em] text-white/45">{labels[auth.merchant]}</p>
              <h1 className="mt-2 text-2xl font-semibold tracking-[-0.03em]">Cited chat</h1>
              <p className="mt-1 text-xs text-white/45">Every number traces back to source</p>
            </div>
            <div className="mt-4 grid gap-2 lg:grid-cols-3">
              {prompts.map((prompt) => (
                <button
                  key={prompt}
                  onClick={() => setInput(prompt)}
                  className="min-h-12 rounded-xl border border-white/10 bg-white/[0.04] px-4 py-3 text-left text-sm font-medium leading-5 text-white/65 transition hover:border-emerald-200/40 hover:bg-emerald-200/10 hover:text-white"
                >
                  {prompt}
                </button>
              ))}
            </div>
          </div>
          <div className="flex-1 space-y-5 overflow-auto p-5">
            {messages.length === 0 ? (
              <div className="grid min-h-80 place-items-center px-6 text-center">
                <div>
                  <div className="mx-auto mb-5 grid size-10 place-items-center rounded-full border border-emerald-200/20 bg-emerald-200/10 text-sm font-semibold text-emerald-100">
                    D
                  </div>
                  <p className="text-lg font-semibold text-white">Ask a merchant ops question</p>
                  <p className="mt-3 max-w-md text-sm leading-6 text-white/48">
                    Answers include cited source rows, and the evidence panel keeps raw API lineage one click away.
                  </p>
                </div>
              </div>
            ) : null}
            {messages.map((message, index) => {
              if (message.role === "assistant" && !message.content.trim()) return null;
              return (
                <div key={index} className={`flex gap-3 ${message.role === "user" ? "justify-end" : "justify-start"}`}>
                  {message.role === "assistant" ? <Avatar label="D" /> : null}
                  <div className={`max-w-[min(76%,760px)] ${message.role === "user" ? "items-end" : "items-start"} flex flex-col gap-1.5`}>
                    <div className={`px-4 py-3 text-sm leading-6 shadow-2xl ${
                      message.role === "user"
                        ? "rounded-[22px] rounded-br-md bg-white text-black shadow-white/5"
                        : "rounded-[22px] rounded-bl-md border border-emerald-200/20 bg-emerald-200/10 text-white shadow-black/25"
                    }`}
                    >
                      {message.role === "assistant" ? (
                        <CitationText text={message.content} onCitation={pinCitation} />
                      ) : (
                        message.content
                      )}
                    </div>
                    <div className="px-2 text-[11px] font-semibold uppercase tracking-[0.2em] text-white/30">
                      {message.role === "assistant" ? "Drishti" : "You"}
                    </div>
                  </div>
                  {message.role === "user" ? <Avatar label="Y" muted /> : null}
                </div>
              );
            })}
            {busy ? (
              <div className="flex justify-start gap-3">
                <Avatar label="D" />
                <div className="rounded-[22px] rounded-bl-md border border-emerald-200/20 bg-emerald-200/10 px-4 py-3">
                  <div className="flex h-5 items-center gap-1.5">
                    <span className="size-2 animate-bounce rounded-full bg-emerald-200/45 [animation-delay:-0.24s]" />
                    <span className="size-2 animate-bounce rounded-full bg-emerald-200/65 [animation-delay:-0.12s]" />
                    <span className="size-2 animate-bounce rounded-full bg-emerald-200/85" />
                  </div>
                </div>
              </div>
            ) : null}
          </div>
          <form onSubmit={send} className="border-t border-white/10 bg-black/35 p-4">
            <div className="flex items-center gap-2 rounded-full border border-white/10 bg-black/30 p-1.5 shadow-[inset_0_1px_0_rgba(255,255,255,0.05)] transition focus-within:border-emerald-200/40 focus-within:bg-black/40">
              <input
                value={input}
                onChange={(event) => setInput(event.target.value)}
                className="chat-composer-input h-11 min-w-0 flex-1 appearance-none border-0 bg-transparent px-5 text-sm text-white outline-none ring-0 placeholder:text-white/30 focus:border-0 focus:outline-none focus:ring-0 focus-visible:outline-none"
                placeholder="Ask anything across your tools…"
              />
              <button
                disabled={busy || !auth.token}
                className="h-11 rounded-full bg-white px-6 text-sm font-semibold text-black transition hover:bg-emerald-100 disabled:cursor-not-allowed disabled:bg-white/40"
              >
                {busy ? "Sending…" : "Send"}
              </button>
            </div>
          </form>
        </section>

        <aside className="grid content-start gap-5 xl:col-span-4">
          <section className="overflow-hidden rounded-2xl border border-white/10 bg-white/[0.025] shadow-2xl shadow-black/40">
            <div className="flex items-center justify-between border-b border-white/10 bg-black/30 px-4 py-3">
              <h2 className="text-sm font-semibold text-white">Evidence rows</h2>
              <span className="rounded-full bg-emerald-300/15 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.16em] text-emerald-100 ring-1 ring-emerald-200/25">{lastRows.length}</span>
            </div>
            <div className="max-h-72 overflow-auto p-2">
              {busy && lastRows.length === 0 ? <EvidenceRowsSkeleton /> : null}
              {lastRows.map((row) => (
                <button
                  key={row.row_id}
                  onClick={() => loadRaw(row)}
                  className={`block w-full rounded-md px-3 py-2 text-left transition ${
                    selectedRowId === row.row_id
                      ? "bg-emerald-200/10 ring-1 ring-emerald-200/25"
                      : "hover:bg-white/[0.05]"
                  }`}
                >
                  <span className="block truncate font-mono text-xs font-semibold text-white">{row.row_id}</span>
                  <span className="mt-1 block truncate text-xs text-white/40">{row.fetched_from}</span>
                  {!row.raw_record_id ? (
                    <span className="mt-1 block text-xs font-medium text-emerald-100/70">Derived evidence</span>
                  ) : null}
                </button>
              ))}
              {!busy && lastRows.length === 0 ? <p className="p-4 text-sm text-white/45">No evidence rows yet.</p> : null}
            </div>
          </section>
          <section className="overflow-hidden rounded-2xl border border-white/10 bg-white/[0.025] shadow-2xl shadow-black/40">
            <div className="border-b border-white/10 bg-black/30 px-4 py-3">
              <h2 className="text-sm font-semibold text-white">Evidence detail</h2>
            </div>
            {isAggregateRaw(raw) ? <AggregateDetail raw={raw} /> : null}
            {raw?.status === "loading" ? (
              <div className="p-4">
                <SkeletonLine className="h-4 w-3/4" />
                <SkeletonLine className="mt-3 h-4 w-11/12" />
                <SkeletonLine className="mt-3 h-4 w-2/3" />
              </div>
            ) : (
              <pre className="max-h-[48vh] overflow-auto p-4 text-xs leading-5 text-white/62">
                {raw ? JSON.stringify(raw, null, 2) : "Select an evidence row."}
              </pre>
            )}
          </section>
        </aside>
      </div>
    </main>
  );
}

function ChatHistorySkeleton() {
  return (
    <>
      {[0, 1, 2].map((index) => (
        <div key={index} className="mb-2 rounded-md border border-white/10 bg-black/20 px-3 py-3">
          <SkeletonLine className="h-4 w-4/5" />
          <SkeletonLine className="mt-2 h-3 w-3/5" />
        </div>
      ))}
    </>
  );
}

function EvidenceRowsSkeleton() {
  return (
    <>
      {[0, 1, 2].map((index) => (
        <div key={index} className="rounded-md px-3 py-2">
          <SkeletonLine className="h-4 w-32" />
          <SkeletonLine className="mt-2 h-3 w-24" />
        </div>
      ))}
    </>
  );
}

function Avatar({ label, muted = false }: { label: string; muted?: boolean }) {
  return (
    <div
      className={`mt-1 grid size-8 shrink-0 place-items-center rounded-full text-xs font-semibold ${
        muted
          ? "border border-white/10 bg-white/[0.06] text-white/55"
          : "bg-emerald-200 text-black shadow-[0_0_28px_rgba(110,231,183,0.2)]"
      }`}
    >
      {label}
    </div>
  );
}

function AggregateDetail({ raw }: { raw: Record<string, unknown> }) {
  const orderIds = asStringArray(raw.contributing_order_ids);
  const shipmentIds = asStringArray(raw.contributing_shipment_ids);
  return (
    <div className="grid gap-3 border-b border-white/10 bg-emerald-200/[0.06] p-4">
      <div>
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-emerald-100/60">Aggregate</p>
        <p className="mt-1 text-sm font-semibold text-white">{String(raw.label || raw.id)}</p>
        <p className="mt-1 text-xs leading-5 text-white/50">{String(raw.formula || "")}</p>
      </div>
      <ContributorList title="Orders" ids={orderIds} />
      <ContributorList title="Shipments" ids={shipmentIds} />
    </div>
  );
}

function ContributorList({ title, ids }: { title: string; ids: string[] }) {
  return (
    <div className="rounded-md border border-white/10 bg-black/25 p-3">
      <div className="flex items-center justify-between gap-3">
        <span className="text-xs font-semibold uppercase tracking-[0.18em] text-white/35">{title}</span>
        <span className="rounded-full bg-white/10 px-2 py-0.5 text-xs font-semibold text-white/60">{ids.length}</span>
      </div>
      <div className="mt-2 flex max-h-20 flex-wrap gap-1 overflow-auto">
        {ids.slice(0, 40).map((id) => (
          <span key={id} className="rounded bg-white/10 px-2 py-1 font-mono text-[11px] text-white/68">
            {id}
          </span>
        ))}
        {ids.length > 40 ? <span className="px-2 py-1 text-xs text-white/45">+{ids.length - 40} more</span> : null}
        {ids.length === 0 ? <span className="text-xs text-white/42">No direct IDs on this aggregate.</span> : null}
      </div>
    </div>
  );
}

function parseSse(frame: string): { event: string; data: Record<string, unknown> } | null {
  const event = frame
    .split("\n")
    .find((line) => line.startsWith("event: "))
    ?.slice(7);
  const data = frame
    .split("\n")
    .find((line) => line.startsWith("data: "))
    ?.slice(6);
  if (!event || !data) return null;
  return { event, data: JSON.parse(data) };
}

function collectContributorIds(rows: ToolRow[], kind: "order" | "shipment") {
  const ids = new Set<string>();
  const singleKey = `${kind}_id`;
  const arrayKeys = [`${kind}_ids`, `contributing_${kind}_ids`];
  for (const row of rows) {
    if (row.row_id.startsWith(`${kind}:`)) ids.add(row.row_id);
    const singleValue = row.values[singleKey];
    if (typeof singleValue === "string") ids.add(`${kind}:${singleValue}`);
    for (const key of arrayKeys) {
      const value = row.values[key];
      if (Array.isArray(value)) {
        for (const item of value) {
          if (typeof item === "string") ids.add(item.startsWith(`${kind}:`) ? item : `${kind}:${item}`);
        }
      }
    }
  }
  return Array.from(ids);
}

function isAggregateRaw(raw: Record<string, unknown> | null): raw is Record<string, unknown> {
  return raw?.type === "aggregate";
}

function asStringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function formatRelative(isoTimestamp: string) {
  const ts = new Date(isoTimestamp).getTime();
  if (Number.isNaN(ts)) return "";
  const diff = Date.now() - ts;
  const sec = Math.round(diff / 1000);
  if (sec < 60) return "Just now";
  const min = Math.round(sec / 60);
  if (min < 60) return `${min}m ago`;
  const hr = Math.round(min / 60);
  if (hr < 24) return `${hr}h ago`;
  const day = Math.round(hr / 24);
  return `${day}d ago`;
}
