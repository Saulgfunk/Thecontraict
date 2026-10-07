import Link from "next/link";

const FEATURES = [
  {
    title: "Never miss a notice deadline",
    body: "Renewal, non-renewal and termination notice dates are extracted from your contracts and calculated for you, with business days and public holidays.",
  },
  {
    title: "Every date shows its source",
    body: "Each deadline links to the clause it came from and explains the calculation, so your team can verify it in seconds.",
  },
  {
    title: "Built for legal teams and firms",
    body: "Separate workspaces per client, entity or department, with access controls and a full audit trail.",
  },
];

export default function Home() {
  return (
    <main className="mx-auto flex min-h-screen max-w-5xl flex-col px-6 py-10">
      <header className="flex items-center justify-between">
        <span className="text-lg font-semibold">
          TheContr<span className="text-primary">AI</span>ct
        </span>
        <Link href="/app" className="text-primary text-sm font-medium hover:underline">
          Sign in
        </Link>
      </header>

      <section className="py-20">
        <h1 className="max-w-3xl text-4xl font-semibold tracking-tight sm:text-5xl">
          Contract deadlines, notice periods and invoices — tracked for you.
        </h1>
        <p className="text-muted mt-5 max-w-2xl text-lg">
          Upload contracts, let AI find every renewal date, notice period and payment term, and get
          alerted well before anything is due. Ask questions about any contract and get answers with
          clause citations.
        </p>
        <Link
          href="/app"
          className="bg-primary text-primary-foreground mt-8 inline-flex h-11 items-center rounded-md px-6 font-medium hover:opacity-90"
        >
          Open the app
        </Link>
      </section>

      <section className="grid gap-6 sm:grid-cols-3">
        {FEATURES.map((f) => (
          <div key={f.title} className="border-border bg-surface rounded-lg border p-5">
            <h2 className="font-semibold">{f.title}</h2>
            <p className="text-muted mt-2 text-sm">{f.body}</p>
          </div>
        ))}
      </section>
    </main>
  );
}
