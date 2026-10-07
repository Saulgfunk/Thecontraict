"use client";

import { SignIn } from "@clerk/nextjs";
import { Check } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { Logo } from "@/components/app/logo";
import { Button, Field, Input, Loading } from "@/components/ui";
import { setDevEmail, useAuthState } from "@/lib/auth";
import { AUTH_MODE } from "@/lib/config";

function DevSignIn() {
  const [email, setEmail] = useState("");
  return (
    <form
      className="w-full max-w-sm space-y-5"
      onSubmit={(e) => {
        e.preventDefault();
        if (email.trim()) setDevEmail(email.trim().toLowerCase());
      }}
    >
      <div>
        <h1 className="font-serif text-3xl font-medium tracking-tight">Welcome back</h1>
        <p className="text-muted mt-2 text-sm">
          Development mode: any email works locally. Set <code>NEXT_PUBLIC_AUTH_MODE=clerk</code>{" "}
          for real sign-in.
        </p>
      </div>
      <Field label="Email">
        <Input
          type="email"
          required
          autoFocus
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@company.com"
        />
      </Field>
      <Button type="submit" className="h-11 w-full">
        Continue
      </Button>
    </form>
  );
}

export default function SignInPage() {
  const auth = useAuthState();
  const router = useRouter();
  useEffect(() => {
    if (auth.status === "signed-in") router.replace("/app");
  }, [auth.status, router]);

  return (
    <main className="grid min-h-screen lg:grid-cols-2">
      <section className="bg-sidebar text-sidebar-foreground relative hidden flex-col justify-between overflow-hidden p-12 lg:flex">
        <div
          aria-hidden
          className="pointer-events-none absolute -top-40 -right-40 size-[520px] rounded-full bg-[radial-gradient(circle,rgb(76_99_240/0.35),transparent_65%)]"
        />
        <Link href="/" className="relative">
          <Logo light />
        </Link>
        <div className="relative max-w-md">
          <p className="font-serif text-4xl leading-tight font-medium">
            Every renewal, notice and payment date. Handled.
          </p>
          <ul className="text-sidebar-muted mt-8 space-y-3 text-sm">
            {[
              "Deadlines worked out from your contracts, with business days and holidays",
              "Reminders to the right people, well before the date",
              "A record of every decision your team makes",
            ].map((t) => (
              <li key={t} className="flex gap-3">
                <Check className="text-accent mt-0.5 size-4 shrink-0" /> {t}
              </li>
            ))}
          </ul>
        </div>
        <p className="text-sidebar-muted relative text-xs">
          For in-house legal teams and law firms
        </p>
      </section>
      <section className="flex flex-col items-center justify-center gap-10 px-6 py-12">
        <Link href="/" className="lg:hidden">
          <Logo />
        </Link>
        {AUTH_MODE === "clerk" ? (
          // Clerk reads the URL, which Next.js only allows inside a Suspense boundary.
          <Suspense fallback={<Loading />}>
            <SignIn forceRedirectUrl="/app" />
          </Suspense>
        ) : (
          <DevSignIn />
        )}
      </section>
    </main>
  );
}
