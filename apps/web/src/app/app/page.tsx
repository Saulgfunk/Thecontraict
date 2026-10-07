"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { CreateOrganization } from "@/components/app/create-organization";
import { Logo } from "@/components/app/logo";
import { ErrorText, Loading } from "@/components/ui";
import { useMe } from "@/lib/api";
import { useAuthState } from "@/lib/auth";
import { LAST_ORG_KEY } from "@/lib/config";
import { errorMessage } from "@/lib/utils";

export default function AppHome() {
  const me = useMe();
  const auth = useAuthState();
  const router = useRouter();
  const orgs = me.data?.organizations;

  useEffect(() => {
    if (!orgs?.length) return;
    let last: string | null = null;
    try {
      last = window.localStorage.getItem(LAST_ORG_KEY);
    } catch {}
    const target = orgs.find((o) => o.organization.id === last) ?? orgs[0];
    router.replace(`/app/${target.organization.id}`);
  }, [orgs, router]);

  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-4 px-4">
      {me.isPending || orgs?.length ? (
        <Loading />
      ) : me.error ? (
        <ErrorText>Could not reach the API: {errorMessage(me.error)}</ErrorText>
      ) : (
        <>
          <Logo className="mb-4" />
          <CreateOrganization />
          <button className="text-muted text-sm hover:underline" onClick={() => auth.signOut()}>
            Sign out ({auth.email})
          </button>
        </>
      )}
    </main>
  );
}
