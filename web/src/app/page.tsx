"use client";

import { Show, SignInButton, UserButton } from "@clerk/nextjs";
import {
  ArrowUpRight,
  Bot,
  Database,
  Eye,
  Link2,
  Quote,
  ShieldCheck,
} from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { motion, useScroll, useTransform } from "motion/react";
import { useMemo, useRef } from "react";

const TESTIMONIAL =
  "Drishti changed how we look at our business. We finally get answers we can trust, and we're catching costly mistakes we used to miss every week. Drishti changed how we look at our business with answers we can actually trust.";

export default function LandingPage() {
  const disableClerkUi = process.env.NEXT_PUBLIC_E2E_AUTH_BYPASS === "true";

  return (
    <main className="min-h-screen w-full overflow-x-hidden bg-background text-foreground antialiased">
      <Hero disableClerkUi={disableClerkUi} />
      <Testimonial />
      <Features />
      <Process />
      <Stats />
      <FinalCTA />
      <Footer />
    </main>
  );
}

function Hero({ disableClerkUi }: { disableClerkUi: boolean }) {
  const sectionRef = useRef<HTMLElement>(null);
  const { scrollYProgress } = useScroll({
    target: sectionRef,
    offset: ["start start", "end start"],
  });

  const heroY = useTransform(scrollYProgress, [0, 1], [0, -200]);
  const heroOpacity = useTransform(scrollYProgress, [0, 0.5], [1, 0]);
  const dashboardY = useTransform(scrollYProgress, [0, 1], [0, -250]);

  return (
    <section
      ref={sectionRef}
      className="relative h-screen w-full overflow-hidden"
    >
      <nav className="relative z-20 flex items-center justify-between px-8 py-4 md:px-28">
        <div className="flex items-center gap-12 md:gap-20">
          <Link href="/" className="flex items-center gap-2">
            <LogoMark />
            <span className="text-xl font-bold tracking-tight">Drishti</span>
          </Link>
          <div className="hidden items-center gap-1 md:flex">
            <NavLink href="#features">Features</NavLink>
            <NavLink href="#how-it-works">How it works</NavLink>
            <NavLink href="#stats">Why Drishti</NavLink>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {disableClerkUi ? (
            <Link
              href="/dashboard"
              className="rounded-lg bg-foreground px-4 py-2 text-sm font-semibold text-background transition-opacity hover:opacity-90"
            >
              Open dashboard
            </Link>
          ) : (
            <>
              <Show when="signed-out">
                <SignInButton mode="modal">
                  <button className="rounded-lg bg-foreground px-4 py-2 text-sm font-semibold text-background transition-opacity hover:opacity-90">
                    Sign In
                  </button>
                </SignInButton>
              </Show>
              <Show when="signed-in">
                <Link
                  href="/dashboard"
                  className="rounded-lg bg-foreground px-4 py-2 text-sm font-semibold text-background transition-opacity hover:opacity-90"
                >
                  Open dashboard
                </Link>
                <div className="grid size-10 place-items-center rounded-full border border-border/60">
                  <UserButton />
                </div>
              </Show>
            </>
          )}
        </div>
      </nav>

      <motion.div
        style={{ y: heroY, opacity: heroOpacity }}
        className="relative z-10 mt-16 flex flex-col items-center px-4 text-center md:mt-20"
      >
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0 }}
          className="liquid-glass mb-6 inline-flex items-center gap-2 rounded-lg px-3 py-2"
        >
          <span aria-hidden className="relative grid size-2.5 place-items-center">
            <span className="absolute inline-flex size-full animate-ping rounded-full bg-emerald-400 opacity-75" />
            <span className="relative inline-flex size-2 rounded-full bg-emerald-400" />
          </span>
          <span className="text-sm font-medium text-foreground">
            Watching your D2C stack, around the clock
          </span>
        </motion.div>

        <motion.h1
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.1 }}
          className="mb-3 text-5xl font-medium leading-tight tracking-[-2px] md:text-7xl md:leading-[1.15]"
        >
          Your Insights.
          <br />
          One Clear{" "}
          <span className="font-serif font-normal italic">Overview.</span>
        </motion.h1>

        <motion.p
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.2 }}
          style={{ color: "hsl(var(--hero-subtitle))" }}
          className="mb-8 max-w-xl text-lg font-normal leading-6 opacity-90"
        >
          Drishti pulls your commerce, logistics, and payments tools
          <br />
          into one place , so the answers you need come with the proof.
        </motion.p>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.3 }}
        >
          <motion.div
            whileHover={{ scale: 1.03 }}
            whileTap={{ scale: 0.98 }}
            className="inline-block"
          >
            <Link
              href="/dashboard"
              className="inline-flex items-center rounded-full bg-foreground px-8 py-3.5 text-base font-medium text-background"
            >
              Get Started for Free
            </Link>
          </motion.div>
        </motion.div>
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 40 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.8, delay: 0.4 }}
        style={{
          width: "100vw",
          marginLeft: "calc(-50vw + 50%)",
          aspectRatio: "16 / 9",
        }}
        className="relative mt-12"
      >
        <video
          autoPlay
          loop
          muted
          playsInline
          className="absolute inset-0 h-full w-full object-cover"
        >
          <source
            src="https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260307_083826_e938b29f-a43a-41ec-a153-3d4730578ab8.mp4"
            type="video/mp4"
          />
        </video>

        <motion.div
          style={{ y: dashboardY, mixBlendMode: "luminosity" }}
          className="absolute left-1/2 top-1/2 w-[90%] max-w-5xl -translate-x-1/2 -translate-y-1/2 overflow-hidden rounded-2xl"
        >
          <DashboardMockup />
        </motion.div>

        <div className="pointer-events-none absolute inset-x-0 bottom-0 z-30 h-40 bg-gradient-to-b from-transparent to-background" />
      </motion.div>
    </section>
  );
}

function Testimonial() {
  const containerRef = useRef<HTMLDivElement>(null);
  const { scrollYProgress } = useScroll({
    target: containerRef,
    offset: ["start end", "end center"],
  });

  const words = useMemo(() => TESTIMONIAL.split(" "), []);

  return (
    <section className="flex min-h-screen items-center justify-center px-8 py-24 md:px-28 md:py-32">
      <div
        ref={containerRef}
        className="mx-auto flex w-full max-w-3xl flex-col items-start gap-10"
      >
        <QuoteSymbol />

        <p className="flex flex-wrap text-4xl font-medium leading-[1.2] md:text-5xl">
          {words.map((word, index) => (
            <RevealWord
              key={index}
              word={word}
              index={index}
              total={words.length}
              progress={scrollYProgress}
            />
          ))}
          <span className="ml-2 text-muted-foreground">&rdquo;</span>
        </p>

        <div className="flex items-center gap-4">
          <AvatarPlaceholder />
          <div className="flex flex-col">
            <span className="text-base font-semibold leading-7 text-foreground">
              Saahil Goel
            </span>
            <span className="text-sm font-normal leading-5 text-muted-foreground">
              CEO, Shiprocket
            </span>
          </div>
        </div>
      </div>
    </section>
  );
}

function RevealWord({
  word,
  index,
  total,
  progress,
}: {
  word: string;
  index: number;
  total: number;
  progress: ReturnType<typeof useScroll>["scrollYProgress"];
}) {
  const start = index / total;
  const end = (index + 1) / total;
  const opacity = useTransform(progress, [start, end], [0.2, 1]);
  const color = useTransform(
    progress,
    [start, end],
    ["hsl(0 0% 35%)", "hsl(0 0% 100%)"],
  );

  return (
    <motion.span style={{ opacity, color }} className="mr-[0.3em]">
      {word}
    </motion.span>
  );
}

function NavLink({
  href,
  children,
  trailing,
}: {
  href: string;
  children: React.ReactNode;
  trailing?: React.ReactNode;
}) {
  return (
    <Link
      href={href}
      className="flex items-center gap-1 rounded-md px-3 py-1.5 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground"
    >
      {children}
      {trailing}
    </Link>
  );
}

function LogoMark() {
  return (
    <span
      aria-hidden
      className="relative grid size-10 place-items-center rounded-full text-background"
      style={{
        background:
          "radial-gradient(circle at 32% 28%, #ffffff 0%, #e4e4e7 60%, #a1a1aa 100%)",
        boxShadow:
          "0 0 28px rgba(255,255,255,0.22), inset 0 -3px 6px rgba(0,0,0,0.18), inset 0 1px 1px rgba(255,255,255,0.85)",
      }}
    >
      <Eye className="size-5" strokeWidth={2.25} />
      <span
        aria-hidden
        className="pointer-events-none absolute inset-0 rounded-full"
        style={{
          boxShadow: "inset 0 0 0 1px rgba(0,0,0,0.08)",
        }}
      />
    </span>
  );
}

function QuoteSymbol() {
  return (
    <svg
      aria-hidden
      viewBox="0 0 56 40"
      className="h-10 w-14 text-foreground"
      fill="currentColor"
    >
      <path d="M0 40V24C0 14 4.5 6 14 0L20 6C13 11 10 16 10 22H22V40H0ZM34 40V24C34 14 38.5 6 48 0L54 6C47 11 44 16 44 22H56V40H34Z" />
    </svg>
  );
}

function AvatarPlaceholder() {
  return (
    <Image
      src="/saahil-goel.jpg"
      alt="Saahil Goel"
      width={56}
      height={56}
      className="size-14 rounded-full border-[3px] border-foreground object-cover"
      priority={false}
    />
  );
}

function DashboardMockup() {
  const metrics = [
    { label: "Open findings", value: "17", trend: "+3 today" },
    { label: "High severity", value: "5", trend: "2 unresolved" },
    { label: "Savings low", value: "₹2.4L", trend: "30-day est." },
    { label: "Savings high", value: "₹4.1L", trend: "30-day est." },
  ];

  const findings = [
    {
      severity: "high",
      duty: "cod_rto_risk",
      type: "COD RTO pincode cluster",
      range: "₹38,200 – ₹54,600",
      rows: 24,
    },
    {
      severity: "high",
      duty: "courier_margin_drift",
      type: "Courier margin drift route",
      range: "₹19,800 – ₹26,400",
      rows: 18,
    },
    {
      severity: "medium",
      duty: "refund_shipping_mismatch",
      type: "Refund shipping mismatch",
      range: "₹12,300 – ₹17,900",
      rows: 9,
    },
    {
      severity: "medium",
      duty: "delayed_prepaid",
      type: "Delayed prepaid shipment",
      range: "₹8,600 – ₹14,200",
      rows: 6,
    },
    {
      severity: "low",
      duty: "cod_rto_risk",
      type: "COD RTO pincode cluster",
      range: "₹3,200 – ₹5,100",
      rows: 4,
    },
  ];

  return (
    <div className="aspect-[16/10] w-full bg-card text-foreground">
      <div className="flex items-center justify-between border-b border-border/40 px-5 py-3">
        <div className="flex items-center gap-6">
          <div className="flex items-center gap-2">
            <span
              aria-hidden
              className="relative grid size-6 place-items-center rounded-full text-background"
              style={{
                background:
                  "radial-gradient(circle at 32% 28%, #ffffff 0%, #e4e4e7 60%, #a1a1aa 100%)",
                boxShadow:
                  "0 0 12px rgba(255,255,255,0.18), inset 0 -2px 4px rgba(0,0,0,0.18), inset 0 1px 1px rgba(255,255,255,0.85)",
              }}
            >
              <Eye className="size-3.5" strokeWidth={2.25} />
              <span
                aria-hidden
                className="pointer-events-none absolute inset-0 rounded-full"
                style={{ boxShadow: "inset 0 0 0 1px rgba(0,0,0,0.08)" }}
              />
            </span>
            <span className="text-xs font-semibold tracking-tight">Drishti</span>
          </div>
          <div className="flex items-center gap-1 rounded-full border border-border/40 bg-foreground/5 p-0.5 text-[10px] font-medium">
            <span className="rounded-full bg-foreground px-2.5 py-1 text-background">
              Dashboard
            </span>
            <span className="px-2.5 py-1 text-muted-foreground">Chat</span>
            <span className="px-2.5 py-1 text-muted-foreground">Findings</span>
            <span className="px-2.5 py-1 text-muted-foreground">Connections</span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className="rounded-full border border-border/40 bg-foreground/5 px-3 py-1 text-[10px] font-medium text-muted-foreground">
            Merchant C
          </span>
          <span className="grid size-6 place-items-center rounded-full border border-border/40 text-[9px] font-semibold">
            M
          </span>
        </div>
      </div>

      <div className="grid gap-3 p-5">
        <div className="flex items-end justify-between">
          <div>
            <p className="text-[9px] font-semibold uppercase tracking-[0.22em] text-muted-foreground">
              Merchant C
            </p>
            <h3 className="mt-1 text-2xl font-semibold tracking-[-0.03em]">
              Ops dashboard
            </h3>
          </div>
          <div className="flex items-center gap-2">
            <span className="rounded-full border border-border/40 bg-foreground/5 px-3 py-1.5 text-[10px] font-semibold text-muted-foreground">
              Latest run: 17 findings
            </span>
            <span className="rounded-full bg-foreground px-3 py-1.5 text-[10px] font-semibold text-background">
              Run agent
            </span>
          </div>
        </div>

        <div className="grid grid-cols-4 gap-3">
          {metrics.map((metric) => (
            <div
              key={metric.label}
              className="rounded-lg border border-border/40 bg-foreground/[0.04] p-3"
            >
              <p className="text-[9px] font-medium uppercase tracking-[0.18em] text-muted-foreground">
                {metric.label}
              </p>
              <p className="mt-2 text-xl font-semibold tracking-[-0.02em]">
                {metric.value}
              </p>
              <p className="mt-1 text-[9px] text-muted-foreground">
                {metric.trend}
              </p>
            </div>
          ))}
        </div>

        <div className="grid grid-cols-[1fr_220px] gap-3">
          <div className="rounded-lg border border-border/40 bg-foreground/[0.03]">
            <div className="flex items-center justify-between border-b border-border/40 px-4 py-2.5">
              <span className="text-[11px] font-semibold">Live finding queue</span>
              <span className="text-[9px] font-medium text-muted-foreground">
                Open findings
              </span>
            </div>
            <div className="divide-y divide-border/30">
              {findings.map((finding, index) => (
                <div
                  key={index}
                  className="grid grid-cols-[1fr_auto] gap-3 px-4 py-2.5"
                >
                  <div>
                    <div className="flex items-center gap-2">
                      <span
                        className={`rounded px-1.5 py-0.5 text-[8px] font-semibold uppercase tracking-wide ${severityBadge(
                          finding.severity,
                        )}`}
                      >
                        {finding.severity}
                      </span>
                      <span className="text-[8px] font-medium uppercase tracking-[0.2em] text-muted-foreground">
                        {finding.duty}
                      </span>
                    </div>
                    <p className="mt-1 text-[11px] font-semibold">
                      {finding.type}
                    </p>
                  </div>
                  <div className="text-right">
                    <p className="text-[11px] font-semibold">{finding.range}</p>
                    <p className="mt-0.5 text-[9px] text-muted-foreground">
                      {finding.rows} rows
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="flex flex-col gap-3">
            <div className="rounded-lg border border-border/40 bg-foreground/[0.03] p-3">
              <p className="text-[9px] font-semibold uppercase tracking-[0.2em] text-muted-foreground">
                Source health
              </p>
              <div className="mt-3 space-y-2">
                {[
                  { label: "Shopify", count: 2483 },
                  { label: "Shiprocket", count: 1971 },
                  { label: "Razorpay", count: 2104 },
                ].map((source) => (
                  <div
                    key={source.label}
                    className="flex items-center justify-between text-[10px]"
                  >
                    <div className="flex items-center gap-1.5">
                      <span className="size-1.5 rounded-full bg-foreground" />
                      <span className="font-semibold">{source.label}</span>
                    </div>
                    <span className="text-muted-foreground">{source.count}</span>
                  </div>
                ))}
              </div>
            </div>
            <div className="flex-1 rounded-lg border border-border/40 bg-foreground/[0.03] p-3">
              <p className="text-[9px] font-semibold uppercase tracking-[0.2em] text-muted-foreground">
                Daily freight
              </p>
              <div className="mt-3 flex h-16 items-end gap-1">
                {Array.from({ length: 14 }).map((_, index) => (
                  <div
                    key={index}
                    className="flex-1 rounded-sm bg-foreground/70"
                    style={{
                      height: `${35 + Math.sin(index * 0.85) * 22 + index * 2.5}%`,
                    }}
                  />
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function severityBadge(severity: string) {
  if (severity === "high") return "bg-foreground/85 text-background";
  if (severity === "medium") return "bg-foreground/40 text-foreground";
  return "bg-foreground/15 text-foreground";
}

function Features() {
  const features = [
    {
      icon: Link2,
      title: "Your whole stack, one view",
      body: "Shopify, Shiprocket, and Razorpay in one place. Swap tools or add new ones as your business grows — Drishti keeps everything in step.",
    },
    {
      icon: Database,
      title: "Every answer shows its work",
      body: "Every number traces back to the order, shipment, or payment it came from. No more stitching exports together in a spreadsheet.",
    },
    {
      icon: Quote,
      title: "Answers you can trust",
      body: "Drishti shows the receipts on every claim. If something isn't backed by your data, it doesn't make it into the answer.",
    },
    {
      icon: Bot,
      title: "An employee that never sleeps",
      body: "A built-in agent keeps an eye on your business and flags where money is leaking — risky orders, courier overcharges, missed refunds — before you have to ask.",
    },
  ];

  return (
    <section
      id="features"
      className="border-t border-border/40 px-8 py-24 md:px-28 md:py-32"
    >
      <div className="mx-auto max-w-6xl">
        <SectionLabel>What you get</SectionLabel>
        <SectionHeading>
          One workspace for{" "}
          <span className="font-serif font-normal italic">commerce</span>,{" "}
          <span className="font-serif font-normal italic">logistics</span>, and{" "}
          <span className="font-serif font-normal italic">money</span>.
        </SectionHeading>

        <div className="mt-16 grid gap-px overflow-hidden rounded-2xl border border-border/40 bg-border/40 md:grid-cols-2">
          {features.map((feature, index) => (
            <motion.div
              key={feature.title}
              initial={{ opacity: 0, y: 24 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, amount: 0.3 }}
              transition={{ duration: 0.6, delay: index * 0.08 }}
              className="bg-background p-8 md:p-10"
            >
              <feature.icon
                className="size-6 text-foreground"
                strokeWidth={1.5}
              />
              <h3 className="mt-6 text-xl font-semibold tracking-tight md:text-2xl">
                {feature.title}
              </h3>
              <p className="mt-3 text-base leading-7 text-muted-foreground">
                {feature.body}
              </p>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}

function Process() {
  const steps = [
    {
      number: "01",
      title: "Connect your tools",
      body: "Sign in once. Drishti pulls in your history and keeps everything in sync from there.",
    },
    {
      number: "02",
      title: "We do the boring part",
      body: "Drishti lines up your orders, shipments, and payments across every tool — so they actually make sense together.",
    },
    {
      number: "03",
      title: "Ask anything",
      body: "Ask a question in plain English. Drishti answers with the proof, and the agent flags things worth fixing.",
    },
  ];

  return (
    <section
      id="how-it-works"
      className="border-t border-border/40 px-8 py-24 md:px-28 md:py-32"
    >
      <div className="mx-auto max-w-6xl">
        <SectionLabel>How it works</SectionLabel>
        <SectionHeading>
          From scattered tools to{" "}
          <span className="font-serif font-normal italic">clear</span> answers,
          fast.
        </SectionHeading>

        <div className="mt-16 grid gap-8 md:grid-cols-3">
          {steps.map((step, index) => (
            <motion.div
              key={step.number}
              initial={{ opacity: 0, y: 24 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, amount: 0.4 }}
              transition={{ duration: 0.6, delay: index * 0.1 }}
              className="relative rounded-2xl border border-border/40 bg-card/40 p-8"
            >
              <span className="font-serif text-5xl font-normal italic text-foreground/30">
                {step.number}
              </span>
              <h3 className="mt-6 text-xl font-semibold tracking-tight">
                {step.title}
              </h3>
              <p className="mt-3 text-base leading-7 text-muted-foreground">
                {step.body}
              </p>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}

function Stats() {
  const stats = [
    {
      value: "3",
      suffix: "tools",
      label: "Shopify, Shiprocket, and Razorpay — all talking to each other.",
    },
    {
      value: "100%",
      suffix: "cited",
      label: "Every number you see is backed by real data from your business.",
    },
    {
      value: "10k",
      suffix: "brands",
      label: "Built to handle thousands of brands at once, not just one.",
    },
  ];

  return (
    <section
      id="stats"
      className="border-t border-border/40 px-8 py-24 md:px-28 md:py-32"
    >
      <div className="mx-auto max-w-6xl">
        <SectionLabel>By the numbers</SectionLabel>
        <SectionHeading>
          Built for the{" "}
          <span className="font-serif font-normal italic">long tail</span> of D2C
          ops.
        </SectionHeading>

        <div className="mt-16 grid gap-px overflow-hidden rounded-2xl border border-border/40 bg-border/40 md:grid-cols-3">
          {stats.map((stat, index) => (
            <motion.div
              key={stat.value}
              initial={{ opacity: 0, y: 24 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, amount: 0.4 }}
              transition={{ duration: 0.6, delay: index * 0.1 }}
              className="bg-background p-8 md:p-10"
            >
              <div className="flex items-baseline gap-2">
                <span className="text-6xl font-medium tracking-[-2px] md:text-7xl">
                  {stat.value}
                </span>
                <span className="text-base font-medium text-muted-foreground">
                  {stat.suffix}
                </span>
              </div>
              <p className="mt-4 text-base leading-7 text-muted-foreground">
                {stat.label}
              </p>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}

function FinalCTA() {
  return (
    <section className="border-t border-border/40 px-8 py-24 md:px-28 md:py-40">
      <motion.div
        initial={{ opacity: 0, y: 30 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, amount: 0.4 }}
        transition={{ duration: 0.7 }}
        className="mx-auto flex max-w-4xl flex-col items-center text-center"
      >
        <div className="liquid-glass mb-8 inline-flex items-center gap-2 rounded-lg px-3 py-2">
          <ShieldCheck className="size-3.5 text-foreground" strokeWidth={2} />
          <span className="text-sm font-medium text-muted-foreground">
            Built for D2C operators
          </span>
        </div>
        <h2 className="text-5xl font-medium leading-tight tracking-[-2px] md:text-7xl md:leading-[1.05]">
          Stop running on{" "}
          <span className="font-serif font-normal italic">vibes</span>.
          <br />
          Start running on{" "}
          <span className="font-serif font-normal italic">evidence</span>.
        </h2>
        <p className="mt-8 max-w-xl text-lg leading-7 text-muted-foreground">
          Connect your tools, ask a question across all of them, and see how
          every answer comes with the proof behind it.
        </p>

        <div className="mt-10 flex items-center justify-center">
          <motion.div whileHover={{ scale: 1.03 }} whileTap={{ scale: 0.98 }}>
            <Link
              href="/dashboard"
              className="inline-flex items-center gap-2 rounded-full bg-foreground px-8 py-3.5 text-base font-medium text-background"
            >
              Get Started for Free
              <ArrowUpRight className="size-4" strokeWidth={2} />
            </Link>
          </motion.div>
        </div>
      </motion.div>
    </section>
  );
}

function Footer() {
  const columns = [
    {
      title: "Product",
      links: [
        { label: "Dashboard", href: "/dashboard", external: false },
        { label: "Chat", href: "/chat", external: false },
        { label: "Findings", href: "/findings", external: false },
        { label: "Connections", href: "/connections", external: false },
      ],
    },
    {
      title: "Stack",
      links: [
        { label: "Shopify", href: "https://www.shopify.com", external: true },
        { label: "Shiprocket", href: "https://www.shiprocket.in", external: true },
        { label: "Razorpay", href: "https://razorpay.com", external: true },
      ],
    },
    {
      title: "Resources",
      links: [
        {
          label: "GitHub",
          href: "https://github.com/mohi-devhub/drishti",
          external: true,
        },
      ],
    },
  ];

  return (
    <footer className="border-t border-border/40 px-8 pb-12 pt-20 md:px-28">
      <div className="mx-auto grid max-w-6xl gap-12 md:grid-cols-[1.4fr_1fr_1fr_1fr]">
        <div>
          <Link href="/" className="flex items-center gap-2">
            <LogoMark />
            <span className="text-xl font-bold tracking-tight">Drishti</span>
          </Link>
          <p className="mt-4 max-w-sm text-sm leading-6 text-muted-foreground">
            The AI ops analyst for D2C brands. Honest answers, money-saving
            insights, and an agent that does the watching for you.
          </p>
        </div>
        {columns.map((column) => (
          <div key={column.title}>
            <p className="text-xs font-semibold uppercase tracking-[0.22em] text-muted-foreground">
              {column.title}
            </p>
            <ul className="mt-4 space-y-3">
              {column.links.map((link) =>
                link.external ? (
                  <li key={link.label}>
                    <a
                      href={link.href}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-sm font-medium text-foreground/80 transition-colors hover:text-foreground"
                    >
                      {link.label}
                    </a>
                  </li>
                ) : (
                  <li key={link.label}>
                    <Link
                      href={link.href}
                      className="text-sm font-medium text-foreground/80 transition-colors hover:text-foreground"
                    >
                      {link.label}
                    </Link>
                  </li>
                ),
              )}
            </ul>
          </div>
        ))}
      </div>
      <div className="mx-auto mt-16 flex max-w-6xl border-t border-border/30 pt-6 text-sm text-muted-foreground">
        <span>© {new Date().getFullYear()} Drishti. All rights reserved.</span>
      </div>
    </footer>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="text-xs font-semibold uppercase tracking-[0.28em] text-muted-foreground">
      {children}
    </p>
  );
}

function SectionHeading({ children }: { children: React.ReactNode }) {
  return (
    <motion.h2
      initial={{ opacity: 0, y: 24 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, amount: 0.4 }}
      transition={{ duration: 0.7 }}
      className="mt-4 max-w-3xl text-4xl font-medium leading-[1.1] tracking-[-1.5px] md:text-6xl md:leading-[1.05]"
    >
      {children}
    </motion.h2>
  );
}
