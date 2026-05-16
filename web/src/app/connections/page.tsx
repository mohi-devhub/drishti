"use client";

import { AlertTriangle, CheckCircle2, Link2, Loader2, ShieldCheck } from "lucide-react";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { AppHeader, apiBase, authHeaders, labels, useDemoAuth } from "../components";

type Connection = {
  source: "shopify" | "shiprocket" | "razorpay";
  status: string;
  display_name: string;
  connected_at: string | null;
  updated_at: string | null;
  last_synced_at: string | null;
  details: Record<string, string | null>;
};

const sources: Connection["source"][] = ["shopify", "shiprocket", "razorpay"];

const sourceLabels: Record<Connection["source"], string> = {
  shopify: "Shopify",
  shiprocket: "Shiprocket",
  razorpay: "Razorpay",
};

export default function ConnectionsPage() {
  const auth = useDemoAuth();
  const [connections, setConnections] = useState<Connection[]>([]);
  const [status, setStatus] = useState("Loading");
  const [busySource, setBusySource] = useState<string | null>(null);
  const [forms, setForms] = useState({
    shopifyShop: "",
    shiprocketEmail: "",
    shiprocketPassword: "",
    shiprocketToken: "",
    shiprocketAccountId: "",
    razorpayKeyId: "",
    razorpayKeySecret: "",
    razorpayAccountId: "",
  });

  const load = useCallback(async () => {
    if (!auth.token) return;
    setStatus("Loading");
    try {
      const response = await fetch(`${apiBase()}/connections`, {
        headers: authHeaders(auth.token),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(JSON.stringify(payload));
      setConnections(payload.connections || []);
      setStatus("Ready");
    } catch (error) {
      console.error(error);
      setStatus("Connections API unavailable");
    }
  }, [auth.token]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void load();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  function update(name: keyof typeof forms, value: string) {
    setForms((current) => ({ ...current, [name]: value }));
  }

  async function startShopify(event: FormEvent) {
    event.preventDefault();
    await submit("shopify", async () => {
      const response = await fetch(`${apiBase()}/connections/shopify/start`, {
        method: "POST",
        headers: { "content-type": "application/json", ...authHeaders(auth.token) },
        body: JSON.stringify({ shop: forms.shopifyShop }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || JSON.stringify(payload));
      window.location.href = payload.install_url;
    });
  }

  async function connectShiprocket(event: FormEvent) {
    event.preventDefault();
    await submit("shiprocket", async () => {
      const response = await fetch(`${apiBase()}/connections/shiprocket`, {
        method: "POST",
        headers: { "content-type": "application/json", ...authHeaders(auth.token) },
        body: JSON.stringify({
          email: forms.shiprocketEmail,
          password: forms.shiprocketPassword,
          token: forms.shiprocketToken || undefined,
          account_id: forms.shiprocketAccountId || undefined,
        }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || JSON.stringify(payload));
      await load();
    });
  }

  async function connectRazorpay(event: FormEvent) {
    event.preventDefault();
    await submit("razorpay", async () => {
      const response = await fetch(`${apiBase()}/connections/razorpay`, {
        method: "POST",
        headers: { "content-type": "application/json", ...authHeaders(auth.token) },
        body: JSON.stringify({
          key_id: forms.razorpayKeyId,
          key_secret: forms.razorpayKeySecret,
          account_id: forms.razorpayAccountId || undefined,
        }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || JSON.stringify(payload));
      await load();
    });
  }

  async function revoke(source: Connection["source"]) {
    await submit(source, async () => {
      const response = await fetch(`${apiBase()}/connections/${source}`, {
        method: "DELETE",
        headers: authHeaders(auth.token),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || JSON.stringify(payload));
      await load();
    });
  }

  async function submit(source: string, action: () => Promise<void>) {
    setBusySource(source);
    setStatus("Saving");
    try {
      await action();
      setStatus("Saved");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Request failed");
    } finally {
      setBusySource(null);
    }
  }

  const bySource = Object.fromEntries(connections.map((connection) => [connection.source, connection]));

  return (
    <main className="min-h-screen text-white">
      <AppHeader
        merchant={auth.merchant}
        token={auth.token}
        error={auth.error}
        authMode={auth.authMode}
        onMerchant={auth.refresh}
      />
      <section className="mx-auto max-w-7xl grid gap-5 px-5 py-8">
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
                {labels[auth.merchant]}
              </p>
              <h1 className="mt-2 text-3xl font-semibold tracking-[-0.04em] sm:text-4xl">
                Connections
              </h1>
              <p className="mt-2 max-w-2xl text-sm leading-6 text-white/55">
                Plug in your commerce, logistics, and payments tools so Drishti has the full picture.
              </p>
            </div>
            <StatusPill status={status} />
          </div>
        </section>

        <div className="grid gap-5 xl:grid-cols-3">
          {sources.map((source) => (
            <section
              key={source}
              className="overflow-hidden rounded-2xl border border-white/10 bg-white/[0.025] shadow-2xl shadow-black/40 transition hover:border-white/15"
            >
              <ConnectionHeader
                connection={bySource[source] as Connection | undefined}
                source={source}
              />
              <div className="grid gap-4 p-5">
                {source === "shopify" ? (
                  <form onSubmit={startShopify} className="grid gap-3">
                    <Field
                      label="Shop domain"
                      requirement="Required"
                      value={forms.shopifyShop}
                      onChange={(value) => update("shopifyShop", value)}
                      placeholder="brand.myshopify.com"
                    />
                    <ActionButton disabled={busySource === source || !auth.token}>
                      Connect Shopify
                    </ActionButton>
                  </form>
                ) : null}
                {source === "shiprocket" ? (
                  <form onSubmit={connectShiprocket} className="grid gap-3">
                    <Field
                      label="Email"
                      requirement="Required"
                      value={forms.shiprocketEmail}
                      onChange={(value) => update("shiprocketEmail", value)}
                      placeholder="ops@example.com"
                    />
                    <Field
                      label="Password"
                      requirement="Required"
                      value={forms.shiprocketPassword}
                      onChange={(value) => update("shiprocketPassword", value)}
                      type="password"
                    />
                    <Field
                      label="Existing bearer token"
                      requirement="Optional"
                      value={forms.shiprocketToken}
                      onChange={(value) => update("shiprocketToken", value)}
                      placeholder="Optional"
                    />
                    <Field
                      label="Company/account ID for webhooks"
                      requirement="Optional"
                      value={forms.shiprocketAccountId}
                      onChange={(value) => update("shiprocketAccountId", value)}
                      placeholder="Optional unless webhooks are enabled"
                    />
                    <ActionButton disabled={busySource === source || !auth.token}>
                      Save Shiprocket credentials
                    </ActionButton>
                  </form>
                ) : null}
                {source === "razorpay" ? (
                  <form onSubmit={connectRazorpay} className="grid gap-3">
                    <Field
                      label="Key ID"
                      requirement="Required"
                      value={forms.razorpayKeyId}
                      onChange={(value) => update("razorpayKeyId", value)}
                      placeholder="rzp_live_..."
                    />
                    <Field
                      label="Key secret"
                      requirement="Required"
                      value={forms.razorpayKeySecret}
                      onChange={(value) => update("razorpayKeySecret", value)}
                      type="password"
                    />
                    <Field
                      label="Account ID for webhooks"
                      requirement="Optional"
                      value={forms.razorpayAccountId}
                      onChange={(value) => update("razorpayAccountId", value)}
                      placeholder="Optional unless webhooks are enabled"
                    />
                    <ActionButton disabled={busySource === source || !auth.token}>
                      Save Razorpay keys
                    </ActionButton>
                  </form>
                ) : null}
                {(bySource[source] as Connection | undefined)?.status === "active" ? (
                  <button
                    onClick={() => revoke(source)}
                    disabled={busySource === source}
                    className="h-10 rounded-full border border-rose-200/25 bg-rose-300/10 px-4 text-sm font-semibold text-rose-100 transition hover:bg-rose-300/15 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    Revoke
                  </button>
                ) : null}
              </div>
            </section>
          ))}
        </div>
      </section>
    </main>
  );
}

function ConnectionHeader({
  connection,
  source,
}: {
  connection?: Connection;
  source: Connection["source"];
}) {
  const status = connection?.status || "not_connected";
  const isActive = status === "active";
  return (
    <div className="border-b border-white/10 bg-black/30 p-5">
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-start gap-3">
          <span className="grid size-10 place-items-center rounded-xl border border-white/10 bg-white/[0.04]">
            <Link2 className="size-4 text-white/70" strokeWidth={2} />
          </span>
          <div>
            <h2 className="text-base font-semibold text-white">{connection?.display_name || sourceLabels[source]}</h2>
            <p className="mt-1 text-xs uppercase tracking-[0.22em] text-white/40">{titleizeStatus(status)}</p>
          </div>
        </div>
        <span
          className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.16em] ring-1 ${
            isActive
              ? "bg-emerald-300/15 text-emerald-100 ring-emerald-200/25"
              : "bg-white/[0.04] text-white/55 ring-white/10"
          }`}
        >
          <span className={`size-1.5 rounded-full ${isActive ? "bg-emerald-300" : "bg-white/40"}`} />
          {isActive ? "Live" : "Off"}
        </span>
      </div>
      <dl className="mt-4 grid gap-2 text-xs">
        {Object.entries(connection?.details || {}).map(([key, value]) => (
          <div key={key} className="grid grid-cols-[88px_1fr] gap-2">
            <dt className="font-medium uppercase tracking-[0.16em] text-white/35">{key}</dt>
            <dd className="truncate text-white/70">{value || "—"}</dd>
          </div>
        ))}
        <div className="grid grid-cols-[88px_1fr] gap-2">
          <dt className="font-medium uppercase tracking-[0.16em] text-white/35">Synced</dt>
          <dd className="truncate text-white/70">{connection?.last_synced_at || "—"}</dd>
        </div>
      </dl>
    </div>
  );
}

function titleizeStatus(status: string) {
  return status.replaceAll("_", " ");
}

function StatusPill({ status }: { status: string }) {
  const isError = status === "Connections API unavailable";
  const isLoading = status === "Loading" || status === "Saving";
  const isReady = status === "Ready" || status === "Saved";
  const icon = isError ? (
    <AlertTriangle className="size-3.5" strokeWidth={2.25} />
  ) : isLoading ? (
    <Loader2 className="size-3.5 animate-spin" strokeWidth={2.25} />
  ) : isReady ? (
    <CheckCircle2 className="size-3.5" strokeWidth={2.25} />
  ) : (
    <ShieldCheck className="size-3.5" strokeWidth={2.25} />
  );
  const classes = isError
    ? "border-rose-300/30 bg-rose-300/10 text-rose-100"
    : isReady
      ? "border-emerald-300/25 bg-emerald-300/10 text-emerald-100"
      : "border-white/10 bg-black/25 text-white/65";
  return (
    <span className={`inline-flex h-11 items-center gap-2 rounded-full border px-4 text-xs font-medium ${classes}`}>
      {icon}
      {status}
    </span>
  );
}

function Field({
  label,
  requirement,
  value,
  onChange,
  placeholder,
  type = "text",
}: {
  label: string;
  requirement?: "Required" | "Optional";
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  type?: string;
}) {
  return (
    <label className="grid gap-2">
      <span className="flex items-center justify-between gap-3">
        <span className="text-xs font-semibold uppercase tracking-[0.18em] text-white/35">{label}</span>
        {requirement ? (
          <span
            className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.12em] ${
              requirement === "Required"
                ? "border-emerald-200/25 bg-emerald-200/10 text-emerald-100/75"
                : "border-white/10 bg-white/[0.05] text-white/38"
            }`}
          >
            {requirement}
          </span>
        ) : null}
      </span>
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        type={type}
        className="h-11 rounded-xl border border-white/10 bg-black/30 px-3.5 text-sm text-white outline-none transition placeholder:text-white/25 focus:border-emerald-200/45 focus:bg-black/40"
      />
    </label>
  );
}

function ActionButton({ children, disabled }: { children: string; disabled?: boolean }) {
  return (
    <button
      disabled={disabled}
      className="h-11 rounded-full bg-white px-5 text-sm font-semibold text-black transition hover:bg-emerald-100 disabled:cursor-not-allowed disabled:bg-white/40"
    >
      {children}
    </button>
  );
}
