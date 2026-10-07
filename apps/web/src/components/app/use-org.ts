"use client";

import { useParams } from "next/navigation";

import { useMe } from "@/lib/api";

/** The current organization (from the URL) and the user's role in it. */
export function useCurrentOrg() {
  const { orgId } = useParams<{ orgId: string }>();
  const me = useMe();
  const entry = me.data?.organizations.find((o) => o.organization.id === orgId);
  return {
    orgId,
    org: entry?.organization,
    role: entry?.role,
    isAdmin: entry?.role === "owner" || entry?.role === "admin",
    isOwner: entry?.role === "owner",
    me: me.data?.user,
  };
}
