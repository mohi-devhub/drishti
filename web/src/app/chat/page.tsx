"use client";

import { FormEvent, Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { AppHeader, CitationText, apiBase, authHeaders, labels, useDemoAuth, type MerchantKey } from "../components";

type ToolRow = {
  row_id: string;
  raw_record_id: string;
  fetched_from: string;
  values: Record<string, unknown>;
};

type Message = {
  role: "user" | "assistant";
  content: string;
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
  const [raw, setRaw] = useState<Record<string, unknown> | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const question = params.get("q");
    if (question) setInput(question);
  }, [params]);

  const switchMerchant = useCallback(
    (merchant: MerchantKey) => {
      setMessages([]);
      setRows([]);
      setRaw(null);
      setSessionId(null);
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
      setRaw(null);
    } catch (error) {
      setMessages((current) => [...current, { role: "assistant", content: `Request failed: ${String(error)}` }]);
    } finally {
      setBusy(false);
    }
  }

  async function loadRaw(row: ToolRow) {
    if (!row.raw_record_id) {
      setRaw({ row_id: row.row_id, fetched_from: row.fetched_from, values: row.values });
      return;
    }
    const response = await fetch(`${apiBase()}/api/source_records/${row.raw_record_id}`, {
      headers: authHeaders(auth.token),
    });
    setRaw(await response.json());
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
      <div className="mx-auto grid max-w-7xl gap-5 px-5 py-6 xl:grid-cols-[minmax(0,1fr)_430px]">
        <section className="flex min-h-[calc(100vh-132px)] flex-col overflow-hidden rounded-lg border border-white/10 bg-white/[0.035] shadow-2xl shadow-black/40">
          <div className="border-b border-white/10 bg-black/25 px-5 py-4">
            <div>
              <p className="text-xs font-medium uppercase tracking-[0.28em] text-white/35">{labels[auth.merchant]}</p>
              <h1 className="mt-1 text-2xl font-semibold tracking-[-0.03em]">Cited chat</h1>
            </div>
            <div className="mt-4 grid gap-2 lg:grid-cols-3">
              {prompts.map((prompt) => (
                <button
                  key={prompt}
                  onClick={() => setInput(prompt)}
                  className="min-h-12 rounded-2xl border border-white/10 bg-white/[0.04] px-4 py-3 text-left text-sm font-medium leading-5 text-white/60 transition hover:border-emerald-200/40 hover:bg-emerald-200/10 hover:text-white"
                >
                  {prompt}
                </button>
              ))}
            </div>
          </div>
          <div className="flex-1 space-y-5 overflow-auto p-5">
            {messages.length === 0 ? (
              <div className="grid min-h-80 place-items-center rounded-lg border border-dashed border-white/15 bg-black/25 p-6 text-center">
                <div>
                  <p className="text-lg font-semibold text-white">Ask a merchant ops question</p>
                  <p className="mt-3 max-w-md text-sm leading-6 text-white/48">
                    Answers include cited source rows, and the evidence panel keeps raw API lineage one click away.
                  </p>
                </div>
              </div>
            ) : null}
            {messages.map((message, index) => (
              <div key={index} className={`flex gap-3 ${message.role === "user" ? "justify-end" : "justify-start"}`}>
                {message.role === "assistant" ? <Avatar label="D" /> : null}
                <div className={`max-w-[min(76%,760px)] ${message.role === "user" ? "items-end" : "items-start"} flex flex-col gap-1.5`}>
                  <div className={`px-4 py-3 text-sm leading-6 shadow-2xl ${
                    message.role === "user"
                      ? "rounded-[22px] rounded-br-md bg-white text-black shadow-white/5"
                      : "rounded-[22px] rounded-bl-md border border-emerald-200/20 bg-emerald-200/10 text-white shadow-black/25"
                  }`}
                  >
                    {message.role === "assistant" ? <CitationText text={message.content} /> : message.content}
                  </div>
                  <div className="px-2 text-[11px] font-semibold uppercase tracking-[0.2em] text-white/30">
                    {message.role === "assistant" ? "Drishti" : "You"}
                  </div>
                </div>
                {message.role === "user" ? <Avatar label="Y" muted /> : null}
              </div>
            ))}
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
          <form onSubmit={send} className="border-t border-white/10 bg-black/30 p-4">
            <div className="flex gap-2 rounded-[28px] border border-white/10 bg-black/40 p-2 shadow-[inset_0_1px_0_rgba(255,255,255,0.05)] focus-within:border-emerald-200/40 focus-within:ring-2 focus-within:ring-emerald-200/10">
              <input
                value={input}
                onChange={(event) => setInput(event.target.value)}
                className="h-11 min-w-0 flex-1 bg-transparent px-4 text-sm text-white outline-none placeholder:text-white/25"
                placeholder="Ask about revenue, returns, shipments, or evidence"
              />
              <button disabled={busy || !auth.token} className="h-11 rounded-full bg-white px-6 text-sm font-semibold text-black transition hover:bg-emerald-100 disabled:cursor-not-allowed disabled:bg-white/55 disabled:text-black/70">
                {busy ? "Sending" : "Send"}
              </button>
            </div>
          </form>
        </section>

        <aside className="grid content-start gap-5">
          <section className="overflow-hidden rounded-lg border border-white/10 bg-white/[0.035] shadow-2xl shadow-black/30">
            <div className="flex items-center justify-between border-b border-white/10 bg-black/25 px-4 py-3">
              <h2 className="text-sm font-semibold">Evidence rows</h2>
              <span className="rounded-full bg-emerald-200/10 px-2 py-1 text-xs font-medium text-emerald-100">{lastRows.length}</span>
            </div>
            <div className="max-h-72 overflow-auto p-2">
              {lastRows.map((row) => (
                <button
                  key={row.row_id}
                  onClick={() => loadRaw(row)}
                  className="block w-full rounded-md px-3 py-2 text-left transition hover:bg-white/[0.05]"
                >
                  <span className="block truncate font-mono text-xs font-semibold text-white">{row.row_id}</span>
                  <span className="mt-1 block truncate text-xs text-white/40">{row.fetched_from}</span>
                  {!row.raw_record_id ? (
                    <span className="mt-1 block text-xs font-medium text-emerald-100/70">Derived evidence</span>
                  ) : null}
                </button>
              ))}
              {lastRows.length === 0 ? <p className="p-4 text-sm text-white/45">No evidence rows yet.</p> : null}
            </div>
          </section>
          <section className="overflow-hidden rounded-lg border border-white/10 bg-white/[0.035] shadow-2xl shadow-black/30">
            <div className="border-b border-white/10 bg-black/25 px-4 py-3">
              <h2 className="text-sm font-semibold">Evidence detail</h2>
            </div>
            <pre className="max-h-[48vh] overflow-auto p-4 text-xs leading-5 text-white/62">
              {raw ? JSON.stringify(raw, null, 2) : "Select an evidence row."}
            </pre>
          </section>
        </aside>
      </div>
    </main>
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
