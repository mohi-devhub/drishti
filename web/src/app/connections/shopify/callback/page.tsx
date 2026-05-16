"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { apiBase, authHeaders, useDemoAuth } from "../../../components";

export default function ShopifyCallbackPage() {
  return (
    <Suspense fallback={<main className="min-h-screen bg-[#050706]" />}>
      <ShopifyCallback />
    </Suspense>
  );
}

function ShopifyCallback() {
  const auth = useDemoAuth();
  const params = useSearchParams();
  const [status, setStatus] = useState("Completing Shopify connection");

  useEffect(() => {
    if (!auth.token) return;
    const payload = Object.fromEntries(params.entries());
    void fetch(`${apiBase()}/connections/shopify/callback`, {
      method: "POST",
      headers: { "content-type": "application/json", ...authHeaders(auth.token) },
      body: JSON.stringify(payload),
    })
      .then(async (response) => {
        const body = await response.json();
        if (!response.ok) throw new Error(body.detail || JSON.stringify(body));
        setStatus("Shopify connected");
      })
      .catch((error) => {
        setStatus(error instanceof Error ? error.message : "Shopify connection failed");
      });
  }, [auth.token, params]);

  return (
    <main className="grid min-h-screen place-items-center bg-[#050706] px-5 text-white">
      <section className="w-full max-w-md rounded-lg border border-white/10 bg-white/[0.04] p-6 shadow-2xl shadow-black/40">
        <p className="text-xs font-semibold uppercase tracking-[0.24em] text-white/35">Shopify</p>
        <h1 className="mt-3 text-2xl font-semibold tracking-[-0.03em]">{status}</h1>
        <Link
          href="/connections"
          className="mt-6 inline-flex h-10 items-center rounded-full bg-white px-4 text-sm font-semibold text-black hover:bg-emerald-100"
        >
          Back to connections
        </Link>
      </section>
    </main>
  );
}
