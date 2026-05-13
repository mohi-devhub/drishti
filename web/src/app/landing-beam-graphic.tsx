"use client";

const sources = [
  { label: "Shopify", x: 52, y: 104 },
  { label: "Shiprocket", x: 52, y: 178 },
  { label: "Razorpay", x: 52, y: 252 },
  { label: "Source records", x: 52, y: 326 },
];

const outputs = [
  { label: "Cited chat", x: 520, y: 126 },
  { label: "Agent findings", x: 520, y: 230 },
  { label: "Raw evidence", x: 520, y: 334 },
];

const inboundPaths = [
  "M 262 104 C 292 104, 300 160, 330 208",
  "M 262 178 C 292 178, 300 198, 330 218",
  "M 262 252 C 292 252, 300 234, 330 230",
  "M 262 326 C 292 326, 300 262, 330 242",
];

const outboundPaths = [
  "M 430 218 C 466 218, 482 126, 520 126",
  "M 430 230 C 466 230, 482 230, 520 230",
  "M 430 242 C 466 242, 482 334, 520 334",
];

export function LandingBeamGraphic() {
  return (
    <div className="relative mx-auto min-h-[430px] w-full max-w-[760px] sm:min-h-[460px]">
      <div className="absolute inset-0 rounded-[40px] bg-emerald-200/5 blur-3xl" />
      <div className="relative h-full min-h-[430px] overflow-hidden rounded-[28px] border border-white/10 bg-white/[0.035] shadow-2xl shadow-black/40 sm:min-h-[460px]">
        <svg className="absolute inset-0 h-full w-full" viewBox="0 0 760 460" preserveAspectRatio="xMidYMid meet" aria-hidden="true">
          <defs>
            <linearGradient id="beamGradient" x1="0" x2="1" y1="0" y2="0">
              <stop offset="0%" stopColor="rgba(167,243,208,0)" />
              <stop offset="42%" stopColor="rgba(167,243,208,0.2)" />
              <stop offset="55%" stopColor="rgba(167,243,208,1)" />
              <stop offset="72%" stopColor="rgba(52,211,153,0.56)" />
              <stop offset="100%" stopColor="rgba(167,243,208,0)" />
            </linearGradient>
            <filter id="beamGlow" x="-20%" y="-80%" width="140%" height="260%">
              <feGaussianBlur stdDeviation="4" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
            <marker id="beamArrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse">
              <path d="M 0 0 L 10 5 L 0 10 z" fill="rgba(167,243,208,0.54)" />
            </marker>
          </defs>

          {[...inboundPaths, ...outboundPaths].map((path, index) => (
            <path
              key={`base-${index}`}
              d={path}
              className="stroke-emerald-100/25"
              strokeWidth="1.7"
              fill="none"
              strokeLinecap="round"
              markerEnd="url(#beamArrow)"
            />
          ))}

          {inboundPaths.map((path, index) => (
            <path
              key={`beam-in-${index}`}
              d={path}
              className="landing-beam-path"
              style={{ animationDelay: `${index * 0.42}s` }}
              stroke="url(#beamGradient)"
              strokeWidth="2.4"
              fill="none"
              strokeLinecap="round"
              pathLength="1"
              filter="url(#beamGlow)"
            />
          ))}
          {outboundPaths.map((path, index) => (
            <path
              key={`beam-out-${index}`}
              d={path}
              className="landing-beam-path"
              style={{ animationDelay: `${1.2 + index * 0.5}s` }}
              stroke="url(#beamGradient)"
              strokeWidth="2.4"
              fill="none"
              strokeLinecap="round"
              pathLength="1"
              filter="url(#beamGlow)"
            />
          ))}

          <circle className="landing-pulse-node" cx="330" cy="230" r="3.5" fill="rgba(167,243,208,0.75)" />
          <circle className="landing-pulse-node" cx="430" cy="230" r="3.5" fill="rgba(167,243,208,0.75)" />
        </svg>

        <div className="absolute left-6 top-8 text-xs font-medium uppercase tracking-[0.24em] text-white/35">Sources</div>
        <div className="absolute right-6 top-8 text-xs font-medium uppercase tracking-[0.24em] text-white/35">Outputs</div>

        {sources.map((source) => (
          <FlowNode key={source.label} label={source.label} x={source.x} y={source.y - 24} />
        ))}

        <div className="absolute left-1/2 top-1/2 grid size-28 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-[28px] border border-emerald-200/30 bg-[#050b08] shadow-[0_0_70px_rgba(110,231,183,0.16)] sm:size-[120px]">
          <div className="text-center">
            <span className="mx-auto grid size-10 place-items-center rounded-full bg-emerald-200 text-sm font-semibold text-black">D</span>
            <h2 className="mt-2 text-2xl font-semibold tracking-[-0.06em] text-white">Drishti</h2>
          </div>
        </div>

        {outputs.map((output) => (
          <FlowNode key={output.label} label={output.label} x={output.x} y={output.y - 24} strong />
        ))}
      </div>
    </div>
  );
}

function FlowNode({
  label,
  x,
  y,
  strong = false,
}: {
  label: string;
  x: number;
  y: number;
  strong?: boolean;
}) {
  return (
    <div
      className={`absolute w-[27.5%] max-w-[210px] rounded-2xl border px-3 py-3 shadow-2xl backdrop-blur sm:px-4 ${
        strong
          ? "border-emerald-200/25 bg-emerald-200/10 text-white"
          : "border-white/10 bg-white/[0.04] text-white/68"
      }`}
      style={{ left: `${(x / 760) * 100}%`, top: `${(y / 460) * 100}%` }}
    >
      <div className="flex items-center gap-2">
        <span className="size-2 shrink-0 rounded-full bg-emerald-300 shadow-[0_0_14px_rgba(110,231,183,0.7)]" />
        <span className="truncate text-sm font-semibold leading-none">{label}</span>
      </div>
    </div>
  );
}
