"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { Loading } from "@/components/ui";
import { useAuthState } from "@/lib/auth";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const auth = useAuthState();
  const router = useRouter();
  useEffect(() => {
    if (auth.status === "signed-out") router.replace("/sign-in");
  }, [auth.status, router]);

  if (auth.status !== "signed-in") {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Loading />
      </div>
    );
  }
  return children;
}
