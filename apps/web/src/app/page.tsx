import { BellRing, FileSearch, ShieldCheck, Users } from "lucide-react";
import Link from "next/link";

import { Logo } from "@/components/app/logo";

const FEATURES = [
  {
    icon: BellRing,
    title: "Never miss a notice deadline",
    body: "Renewal, non-renewal and termination notice dates are worked out for you, with business days and public holidays, and you are reminded well before.",
  },
  {
    icon: FileSearch,
    title: "Every date shows its source",
    body: "Each deadline links to the clause it came from and explains the calculation, so your team can check it in seconds.",
  },
  {
    icon: Users,
    title: "Built for legal teams and firms",
    body: "Keep each client, company or department separate, decide who sees what, and keep a full activity log.",
  },
];

const PREVIEW = [
  {
    month: "Oct",
    day: 2,
    tone: "bg-[#fbe9e7] text-[#c2372c]",
    text: "Last day to tell Swift Freight you don't want to renew",
    sub: "Logistics Services Agreement · in 3 days",
  },
  {
    month: "Nov",
    day: 1,
    tone: "bg-[#fdf1e2] text-[#b8650c]",
    text: "Rent review due",
    sub: "Head Office Lease · in 4 weeks",
  },
  {
    month: "Jan",
    day: 13,
    tone: "bg-[#ebeefe] text-[#3149d8]",
    text: "Last day to tell CloudLedger you don't want to renew",
    sub: "CloudLedger SaaS Subscription · in 3 months",
  },
];

export default function Home() {
  return (
    <div className="relative min-h-screen overflow-hidden">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 top-0 h-[640px] bg-[radial-gradient(60%_60%_at_70%_0%,color-mix(in_srgb,var(--primary)_16%,transparent),transparent),radial-gradient(40%_50%_at_10%_10%,color-mix(in_srgb,var(--accent)_14%,transparent),transparent)]"
      />
      <main className="relative mx-auto flex max-w-6xl flex-col px-6 py-8">
        <header className="flex items-center justify-between">
          <Logo />
          <Link
            href="/app"
            className="border-border bg-surface/70 hover:border-primary/40 hover:text-primary rounded-lg border px-4 py-2 text-sm font-medium backdrop-blur transition"
          >
            Sign in
          </Link>
        </header>

        <section className="grid items-center gap-12 py-16 lg:grid-cols-[1.1fr_1fr] lg:py-24">
          <div className="animate-rise">
            <p className="text-accent mb-4 text-xs font-semibold tracking-[0.16em] uppercase">
              Contract dates, handled
            </p>
            <h1 className="font-serif text-4xl leading-[1.08] font-medium tracking-tight sm:text-6xl">
              Know what&rsquo;s due before it&rsquo;s too late.
            </h1>
            <p className="text-muted mt-6 max-w-xl text-lg">
              Add your contracts and TheContrAIct works out every renewal date, notice period and
              payment, reminds the right people in time, and keeps a record of what you decided.
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-3">
              <Link
                href="/app"
                className="bg-primary text-primary-foreground hover:bg-primary-strong inline-flex h-12 items-center rounded-xl px-6 font-medium shadow-(--shadow-raised) transition"
              >
                Open the app
              </Link>
              <span className="text-muted flex items-center gap-2 text-sm">
                <ShieldCheck className="text-success size-4" /> Each team only sees its own
                contracts
              </span>
            </div>
          </div>

          <div className="animate-rise relative [animation-delay:120ms]">
            <div className="border-border/80 bg-surface rounded-2xl border p-5 shadow-(--shadow-raised)">
              <p className="text-muted text-xs font-semibold tracking-[0.1em] uppercase">
                What needs your attention
              </p>
              <ul className="mt-3 space-y-1">
                {PREVIEW.map((p) => (
                  <li key={p.text} className="flex items-center gap-4 rounded-xl px-1 py-2.5">
                    <span
                      className={`flex size-12 shrink-0 flex-col items-center justify-center rounded-xl ${p.tone}`}
                    >
                      <span className="text-[10px] leading-none font-semibold tracking-wider uppercase">
                        {p.month}
                      </span>
                      <span className="mt-0.5 text-lg leading-none font-semibold">{p.day}</span>
                    </span>
                    <span className="min-w-0">
                      <span className="block text-sm leading-snug font-medium">{p.text}</span>
                      <span className="text-muted block text-xs">{p.sub}</span>
                    </span>
                  </li>
                ))}
              </ul>
              <div className="border-border mt-3 flex gap-2 border-t pt-4">
                {["Renew", "Cancel", "Renegotiate"].map((l) => (
                  <span
                    key={l}
                    className="border-border rounded-full border px-3.5 py-1.5 text-xs font-medium"
                  >
                    {l}
                  </span>
                ))}
              </div>
            </div>
            <div className="bg-sidebar text-sidebar-foreground absolute -bottom-12 left-8 hidden items-center gap-2 rounded-xl px-4 py-3 text-sm shadow-(--shadow-raised) sm:flex">
              <BellRing className="text-accent size-4" /> Reminder sent 90 days before
            </div>
          </div>
        </section>

        <section className="grid gap-5 pb-16 sm:grid-cols-3">
          {FEATURES.map(({ icon: Icon, title, body }) => (
            <div
              key={title}
              className="border-border/80 bg-surface rounded-2xl border p-6 shadow-(--shadow-card)"
            >
              <span className="bg-primary/10 text-primary inline-flex rounded-xl p-2.5">
                <Icon className="size-5" />
              </span>
              <h2 className="mt-4 font-semibold">{title}</h2>
              <p className="text-muted mt-2 text-sm leading-relaxed">{body}</p>
            </div>
          ))}
        </section>
        <footer className="border-border text-muted border-t py-6 text-xs">
          © TheContrAIct · Contract dates, handled
        </footer>
      </main>
    </div>
  );
}
