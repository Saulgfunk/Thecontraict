"use client";

import { useParams } from "next/navigation";

import { AppShell } from "@/components/app/app-shell";

export default function OrgLayout({ children }: { children: React.ReactNode }) {
  const { orgId } = useParams<{ orgId: string }>();
  return <AppShell orgId={orgId}>{children}</AppShell>;
}
