import { Show, SignInButton, SignUpButton, UserButton } from "@clerk/nextjs";
import Link from "next/link";
import { LandingBeamGraphic } from "./landing-beam-graphic";

export default function LandingPage() {
  const disableClerkUi = process.env.NEXT_PUBLIC_E2E_AUTH_BYPASS === "true";

  return (
    <main className="min-h-screen overflow-hidden text-white">
      <header className="mx-auto flex max-w-7xl items-center justify-between px-5 py-8">
        <Link href="/" className="flex items-center gap-3">
          <span className="grid size-11 place-items-center rounded-md bg-white text-sm font-semibold text-black">D</span>
          <span>
            <span className="block text-base font-semibold leading-5 text-white">Drishti</span>
            <span className="block text-sm leading-5 text-white/45">AI ops analyst</span>
          </span>
        </Link>
        <nav className="flex items-center gap-3">
          {disableClerkUi ? (
            <Link className="flex h-11 items-center justify-center rounded-full bg-white px-5 text-sm font-semibold text-black hover:bg-emerald-100" href="/dashboard">
              Open dashboard
            </Link>
          ) : (
            <>
              <Show when="signed-out">
                <SignInButton mode="modal">
                  <button className="flex h-11 items-center justify-center rounded-full border border-white/15 bg-white/[0.04] px-5 text-sm font-semibold text-white hover:border-emerald-200/50 hover:bg-emerald-200/10">
                    Sign in
                  </button>
                </SignInButton>
                <SignUpButton mode="modal">
                  <button className="flex h-11 items-center justify-center rounded-full bg-white px-5 text-sm font-semibold text-black hover:bg-emerald-100">
                    Sign up
                  </button>
                </SignUpButton>
              </Show>
              <Show when="signed-in">
                <Link className="flex h-11 items-center justify-center rounded-full bg-white px-5 text-sm font-semibold text-black hover:bg-emerald-100" href="/dashboard">
                  Open dashboard
                </Link>
                <div className="grid size-11 place-items-center rounded-full border border-white/10 bg-white/[0.06]">
                  <UserButton />
                </div>
              </Show>
            </>
          )}
        </nav>
      </header>

      <section className="mx-auto grid min-h-[calc(100vh-112px)] max-w-7xl items-center gap-12 px-5 pb-14 lg:grid-cols-[0.88fr_1.12fr]">
        <div className="max-w-4xl">
          <div className="flex items-center gap-3 text-xs font-medium uppercase tracking-[0.38em] text-white/45">
            <span className="size-2 rounded-full bg-emerald-300 shadow-[0_0_18px_rgba(110,231,183,0.9)]" />
            D2C Ops Intelligence
          </div>
          <h1 className="mt-16 text-6xl font-semibold leading-[0.96] tracking-[-0.05em] text-white md:text-8xl">
            From scattered data
            <span className="block text-emerald-200">to verified decisions.</span>
          </h1>
          <p className="mt-8 max-w-3xl text-base leading-7 text-white/58 md:text-lg md:leading-8">
            Drishti connects Shopify, Shiprocket, and Razorpay so D2C founders can ask cross-tool questions, inspect cited answers, and review read-only agent findings with raw evidence behind every rupee.
          </p>
          <div className="mt-10 flex flex-wrap gap-3">
            <Link className="flex h-12 items-center justify-center rounded-full bg-white px-6 text-sm font-semibold leading-none text-black shadow-[0_0_40px_rgba(255,255,255,0.16)] hover:bg-emerald-100" href="/dashboard">
              Open dashboard
            </Link>
            <Link className="flex h-12 items-center justify-center rounded-full border border-white/15 bg-white/[0.04] px-6 text-sm font-semibold leading-none text-white hover:border-emerald-200/50 hover:bg-emerald-200/10" href="/chat">
              Ask Drishti
            </Link>
          </div>
        </div>

        <LandingBeamGraphic />
      </section>
    </main>
  );
}
