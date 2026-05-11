const connectors = ["Shopify", "Shiprocket", "Razorpay"];

export default function Home() {
  return (
    <main className="min-h-screen bg-zinc-50 text-zinc-950">
      <section className="mx-auto flex min-h-screen w-full max-w-6xl flex-col justify-between px-6 py-8">
        <header className="flex items-center justify-between border-b border-zinc-200 pb-4">
          <div>
            <p className="text-sm font-medium text-zinc-500">Drishti</p>
            <h1 className="text-2xl font-semibold tracking-normal">Ops workspace</h1>
          </div>
          <span className="rounded-md border border-zinc-300 px-3 py-1 text-sm text-zinc-600">
            Day 0
          </span>
        </header>

        <div className="grid gap-6 py-12 md:grid-cols-[1.2fr_0.8fr]">
          <div className="space-y-6">
            <div>
              <h2 className="max-w-3xl text-4xl font-semibold tracking-normal">
                Cited commerce, shipping, and payment intelligence for D2C ops.
              </h2>
              <p className="mt-4 max-w-2xl text-lg leading-8 text-zinc-600">
                The app shell is ready for the chat, findings, and merchant isolation flows
                described in the build plan.
              </p>
            </div>

            <div className="grid gap-3 sm:grid-cols-3">
              {connectors.map((source) => (
                <div key={source} className="rounded-md border border-zinc-200 bg-white p-4">
                  <p className="text-sm font-medium text-zinc-500">Connector</p>
                  <p className="mt-2 text-lg font-semibold">{source}</p>
                </div>
              ))}
            </div>
          </div>

          <aside className="rounded-md border border-zinc-200 bg-white p-5">
            <h3 className="text-base font-semibold">Local services</h3>
            <dl className="mt-4 space-y-3 text-sm">
              <div className="flex items-center justify-between gap-4">
                <dt className="text-zinc-500">FastAPI</dt>
                <dd className="font-medium">:8000</dd>
              </div>
              <div className="flex items-center justify-between gap-4">
                <dt className="text-zinc-500">Next.js</dt>
                <dd className="font-medium">:3000</dd>
              </div>
              <div className="flex items-center justify-between gap-4">
                <dt className="text-zinc-500">Worker</dt>
                <dd className="font-medium">Arq</dd>
              </div>
            </dl>
          </aside>
        </div>
      </section>
    </main>
  );
}
