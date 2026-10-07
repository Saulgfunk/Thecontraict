"use client";

import { SignIn } from "@clerk/nextjs";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Button, Field, Input } from "@/components/ui";
import { setDevEmail, useAuthState } from "@/lib/auth";
import { AUTH_MODE } from "@/lib/config";

function DevSignIn() {
  const [email, setEmail] = useState("");
  return (
    <form
      className="border-border bg-surface w-full max-w-sm space-y-4 rounded-lg border p-6"
      onSubmit={(e) => {
        e.preventDefault();
        if (email.trim()) setDevEmail(email.trim().toLowerCase());
      }}
    >
      <div>
        <h1 className="text-lg font-semibold">Sign in (development mode)</h1>
        <p className="text-muted mt-1 text-sm">
          Any email works locally. Set <code>NEXT_PUBLIC_AUTH_MODE=clerk</code> for real sign-in.
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
      <Button type="submit" className="w-full">
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
    <main className="flex min-h-screen items-center justify-center px-4">
      {AUTH_MODE === "clerk" ? <SignIn forceRedirectUrl="/app" /> : <DevSignIn />}
    </main>
  );
}
