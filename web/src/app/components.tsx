"use client";

import { Show, SignInButton, SignUpButton, UserButton, useAuth } from "@clerk/nextjs";
import { Eye } from "lucide-react";
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

function demoMerchantSwitcherEnabled(authMode: AuthMode | null) {
  return (
    authMode === "demo" ||
    process.env.NEXT_PUBLIC_ENABLE_DEMO_MERCHANT_SWITCHER === "true"
  );
}

type AuthMode = "clerk" | "demo";

const bypassAuthState = {
  getToken: async () => null,
  isLoaded: true,
  isSignedIn: false,
} as ReturnType<typeof useAuth>;

export function useDemoAuth() {
  const { getToken, isLoaded, isSignedIn } = useClerkAuthState();
  const [merchant, setMerchant] = useState<MerchantKey>("merchant_c");
  const [token, setToken] = useState("");
  const [error, setError] = useState("");

  const authMode: AuthMode | null = !isLoaded
    ? null
    : isSignedIn
      ? "clerk"
      : "demo";

  const setManualToken = useCallback((value: string) => {
    setToken(value);
    localStorage.setItem("drishti.token", value);
  }, []);

  const getFreshToken = useCallback(async (): Promise<string> => {
    if (isLoaded && isSignedIn) {
      const template = process.env.NEXT_PUBLIC_CLERK_JWT_TEMPLATE || undefined;
      const fresh = await getToken(template ? { template } : undefined);
      if (fresh) {
        setToken(fresh);
        return fresh;
      }
    }
    return token;
  }, [getToken, isLoaded, isSignedIn, token]);

  const refresh = useCallback(async (nextMerchant: MerchantKey = "merchant_c") => {
    setError("");
    setMerchant(nextMerchant);
    localStorage.setItem("drishti.merchant", nextMerchant);

    if (isLoaded && isSignedIn) {
      const template = process.env.NEXT_PUBLIC_CLERK_JWT_TEMPLATE || undefined;
      const clerkToken = await getToken(template ? { template } : undefined);
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
      localStorage.setItem("drishti.token", payload.token);
    } catch {
      const stored = localStorage.getItem("drishti.token");
      if (stored) {
        setToken(stored);
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

  return { merchant, token, error, authMode, setToken: setManualToken, refresh, getFreshToken, labels };
}

function useClerkAuthState(): ReturnType<typeof useAuth> {
  if (process.env.NEXT_PUBLIC_E2E_AUTH_BYPASS === "true") {
    return bypassAuthState;
  }
  // This branch is compiled out for E2E builds, where ClerkProvider is intentionally disabled.
  // eslint-disable-next-line react-hooks/rules-of-hooks
  return useAuth();
}

export function AppHeader({
  merchant,
  authMode = null,
  onMerchant,
}: {
  merchant: MerchantKey;
  token: string;
  error: string;
  authMode?: AuthMode | null;
  onMerchant: (merchant: MerchantKey) => void;
}) {
  const pathname = usePathname();
  const showMerchantSwitcher = demoMerchantSwitcherEnabled(authMode);
  const disableClerkUi = process.env.NEXT_PUBLIC_E2E_AUTH_BYPASS === "true";

  return (
    <header className="sticky top-0 z-20 border-b border-white/10 bg-[#050706]/85 backdrop-blur-xl">
      <div className="mx-auto flex max-w-7xl flex-col gap-3 px-5 py-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex flex-wrap items-center gap-4">
          <Link href="/dashboard" className="group flex items-center gap-3">
            <span
              aria-hidden
              className="relative grid size-9 place-items-center rounded-full text-black"
              style={{
                background:
                  "radial-gradient(circle at 32% 28%, #ffffff 0%, #e4e4e7 60%, #a1a1aa 100%)",
                boxShadow:
                  "0 0 24px rgba(255,255,255,0.18), inset 0 -3px 6px rgba(0,0,0,0.18), inset 0 1px 1px rgba(255,255,255,0.85)",
              }}
            >
              <Eye className="size-[18px]" strokeWidth={2.25} />
              <span
                aria-hidden
                className="pointer-events-none absolute inset-0 rounded-full"
                style={{ boxShadow: "inset 0 0 0 1px rgba(0,0,0,0.08)" }}
              />
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
            <NavLink href="/connections" active={pathname === "/connections"}>
              Connections
            </NavLink>
          </nav>
        </div>
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-end">
          {showMerchantSwitcher ? (
            <label className="flex h-11 items-center overflow-hidden rounded-full border border-white/10 bg-white/[0.06] text-white shadow-sm transition focus-within:border-emerald-300/50 focus-within:ring-2 focus-within:ring-emerald-300/15">
              <span className="ml-4 rounded-full border border-emerald-300/20 bg-emerald-300/10 px-2 py-1 text-[10px] font-bold uppercase tracking-[0.16em] text-emerald-200">
                Demo
              </span>
              <select
                value={merchant}
                onChange={(event) => onMerchant(event.target.value as MerchantKey)}
                aria-label="Demo merchant"
                className="h-full min-w-36 bg-transparent py-0 pl-3 pr-5 text-base font-medium leading-none text-white outline-none"
              >
                {(Object.keys(labels) as MerchantKey[]).map((key) => (
                  <option key={key} value={key}>{labels[key]}</option>
                ))}
              </select>
            </label>
          ) : null}
          {!disableClerkUi ? (
            <>
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
            </>
          ) : null}
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

export function CitationText({
  text,
  onCitation,
}: {
  text: string;
  onCitation?: (citationId: string) => void;
}) {
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
          <button
            key={index}
            type="button"
            onClick={() => onCitation?.(part.cite || "")}
            className="rounded bg-amber-300/20 px-1 font-medium text-amber-100 underline decoration-amber-100/35 underline-offset-4 ring-1 ring-amber-200/20 transition hover:bg-amber-300/30"
            title={part.cite}
          >
            {part.text}
          </button>
        ) : (
          <span key={index}>{part.text}</span>
        ),
      )}
    </>
  );
}

const acronymLabels = new Set(["awb", "cod", "rto", "sla"]);

export function titleize(value: string) {
  return value
    .replaceAll("_", " ")
    .split(" ")
    .map((word) => {
      const normalized = word.toLowerCase();
      if (acronymLabels.has(normalized)) return normalized.toUpperCase();
      return word;
    })
    .join(" ");
}

export function money(value: number | null | undefined) {
  return value === null || value === undefined ? "-" : `₹${value.toLocaleString("en-IN")}`;
}

export function moneyRange(low: number | null | undefined, high: number | null | undefined) {
  return low == null && high == null ? "-" : `${money(low)} - ${money(high)}`;
}

export function SkeletonLine({ className = "" }: { className?: string }) {
  return <span className={`block animate-pulse rounded bg-white/10 ${className}`} />;
}
