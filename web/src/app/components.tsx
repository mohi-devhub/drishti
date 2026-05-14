"use client";

import { Show, SignInButton, SignUpButton, UserButton, useAuth } from "@clerk/nextjs";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { useCallback, useEffect, useMemo, useState } from "react";

export type MerchantKey = "merchant_a" | "merchant_b" | "merchant_c";

export const labels: Record<MerchantKey, string> = {
  merchant_a: "Merchant A",
  merchant_b: "Merchant B",
  merchant_c: "Merchant C",
};

export function apiBase() {
  return process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
}

type AuthMode = "clerk" | "demo";

export function useDemoAuth() {
  const { getToken, isLoaded, isSignedIn } = useAuth();
  const [merchant, setMerchant] = useState<MerchantKey>("merchant_c");
  const [token, setToken] = useState("");
  const [error, setError] = useState("");
  const [authMode, setAuthMode] = useState<AuthMode>("demo");

  const setManualToken = useCallback((value: string) => {
    setToken(value);
    localStorage.setItem("drishti.token", value);
  }, []);

  const refresh = useCallback(async (nextMerchant: MerchantKey = "merchant_c") => {
    setError("");
    setMerchant(nextMerchant);
    localStorage.setItem("drishti.merchant", nextMerchant);

    if (isLoaded && isSignedIn) {
      const template = process.env.NEXT_PUBLIC_CLERK_JWT_TEMPLATE || undefined;
      const clerkToken = await getToken(template ? { template } : undefined);
      setAuthMode("clerk");
      if (clerkToken) {
        setToken(clerkToken);
        localStorage.removeItem("drishti.token");
        return;
      }
      setToken("");
      setError("Clerk session did not return a backend token. Check the Clerk JWT template.");
      return;
    }

    try {
      const response = await fetch(`${apiBase()}/demo/token/${nextMerchant}`);
      if (!response.ok) throw new Error(await response.text());
      const payload = await response.json();
      setToken(payload.token);
      setAuthMode("demo");
      localStorage.setItem("drishti.token", payload.token);
    } catch {
      const stored = localStorage.getItem("drishti.token");
      if (stored) {
        setToken(stored);
        setAuthMode("demo");
        setError("");
      } else {
        setError("Demo auth unavailable. Check the local API and DRISHTI_TEST_JWT_SECRET.");
      }
    }
  }, [getToken, isLoaded, isSignedIn]);

  useEffect(() => {
    if (!isLoaded) return undefined;
    const storedMerchant = (localStorage.getItem("drishti.merchant") as MerchantKey | null) || "merchant_c";
    const timer = window.setTimeout(() => {
      void refresh(storedMerchant);
    }, 0);
    return () => window.clearTimeout(timer);
  }, [isLoaded, refresh]);

  return { merchant, token, error, authMode, setToken: setManualToken, refresh, labels };
}

export function AppHeader({
  merchant,
  token,
  error,
  authMode = "demo",
  onMerchant,
}: {
  merchant: MerchantKey;
  token: string;
  error: string;
  authMode?: AuthMode;
  onMerchant: (merchant: MerchantKey) => void;
}) {
  const pathname = usePathname();

  return (
    <header className="sticky top-0 z-20 border-b border-white/10 bg-[#050706]/85 backdrop-blur-xl">
      <div className="mx-auto flex max-w-7xl flex-col gap-3 px-5 py-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex flex-wrap items-center gap-4">
          <Link href="/dashboard" className="group flex items-center gap-3">
            <span className="grid size-9 place-items-center rounded-md border border-white/15 bg-white text-sm font-semibold text-black shadow-[0_0_32px_rgba(255,255,255,0.12)]">
              D
            </span>
            <span>
              <span className="block text-sm font-semibold leading-4 text-white">Drishti</span>
              <span className="block text-xs leading-4 text-white/45">Ops command</span>
            </span>
          </Link>
          <nav className="flex h-11 items-center rounded-full border border-white/10 bg-white/[0.04] p-1 text-sm shadow-[inset_0_1px_0_rgba(255,255,255,0.06)]">
            <NavLink href="/dashboard" active={pathname === "/dashboard"}>
              Dashboard
            </NavLink>
            <NavLink href="/chat" active={pathname === "/chat"}>
              Chat
            </NavLink>
            <NavLink href="/findings" active={pathname === "/findings"}>
              Findings
            </NavLink>
          </nav>
        </div>
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-end">
          <div className="hidden h-11 items-center gap-2 rounded-full border border-emerald-300/20 bg-emerald-300/10 px-5 text-sm font-medium leading-none text-emerald-200 md:flex">
            <span className="size-2 rounded-full bg-emerald-300 shadow-[0_0_14px_rgba(110,231,183,0.8)]" />
            Local demo
          </div>
          <select
            value={merchant}
            onChange={(event) => onMerchant(event.target.value as MerchantKey)}
            className="h-11 rounded-full border border-white/10 bg-white/[0.06] px-5 text-base font-medium leading-none text-white shadow-sm outline-none transition focus:border-emerald-300/50 focus:ring-2 focus:ring-emerald-300/15"
          >
            {(Object.keys(labels) as MerchantKey[]).map((key) => (
              <option key={key} value={key}>{labels[key]}</option>
            ))}
          </select>
          <div
            className="flex h-11 items-center gap-2 rounded-full border border-white/10 bg-white/[0.06] px-5 text-sm font-medium leading-none text-white/70 shadow-sm"
            title={error || (token ? `${authMode === "clerk" ? "Clerk" : "Demo"} auth ready` : "Auth missing")}
          >
            <span className={`size-2 rounded-full ${token ? "bg-emerald-300" : "bg-rose-300"}`} />
            {token ? `${authMode === "clerk" ? "Clerk" : "Demo"} auth` : "Auth missing"}
          </div>
          <Show when="signed-out">
            <SignInButton mode="modal">
              <button className="h-11 rounded-full border border-white/10 bg-white/[0.06] px-5 text-sm font-semibold text-white/80 transition hover:border-emerald-200/40 hover:bg-emerald-200/10 hover:text-white">
                Sign in
              </button>
            </SignInButton>
            <SignUpButton mode="modal">
              <button className="h-11 rounded-full bg-white px-5 text-sm font-semibold text-black transition hover:bg-emerald-100">
                Sign up
              </button>
            </SignUpButton>
          </Show>
          <Show when="signed-in">
            <div className="grid size-11 place-items-center rounded-full border border-white/10 bg-white/[0.06]">
              <UserButton />
            </div>
          </Show>
        </div>
      </div>
    </header>
  );
}

function NavLink({
  href,
  active,
  children,
}: {
  href: string;
  active: boolean;
  children: ReactNode;
}) {
  return (
    <Link
      className={`flex h-9 items-center rounded-full px-4 font-medium leading-none transition ${
        active ? "bg-white text-black shadow-sm" : "text-white/55 hover:text-white"
      }`}
      href={href}
    >
      {children}
    </Link>
  );
}

export function authHeaders(token: string): Record<string, string> {
  return token ? { authorization: `Bearer ${token}` } : {};
}

export function CitationText({ text }: { text: string }) {
  const parts = useMemo(() => {
    const output: Array<{ text: string; cite?: string }> = [];
    const regex = /<cite\s+([^>]+)>(.*?)<\/cite>/g;
    let index = 0;
    for (const match of text.matchAll(regex)) {
      if (match.index > index) output.push({ text: text.slice(index, match.index) });
      output.push({ text: match[2], cite: match[1] });
      index = match.index + match[0].length;
    }
    if (index < text.length) output.push({ text: text.slice(index) });
    return output;
  }, [text]);

  return (
    <>
      {parts.map((part, index) =>
        part.cite ? (
          <span key={index} className="rounded bg-amber-300/20 px-1 font-medium text-amber-100 ring-1 ring-amber-200/20" title={part.cite}>
            {part.text}
          </span>
        ) : (
          <span key={index}>{part.text}</span>
        ),
      )}
    </>
  );
}
