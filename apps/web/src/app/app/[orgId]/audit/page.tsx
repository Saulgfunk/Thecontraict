"use client";

import { useCurrentOrg } from "@/components/app/use-org";
import { Card, ErrorText, Loading, PageHeader } from "@/components/ui";
import { useAuditEvents, useOrgMembers } from "@/lib/api";
import { errorMessage, formatDateTime } from "@/lib/utils";

function describe(data: Record<string, unknown>) {
  return Object.entries(data)
    .filter(([, v]) => v !== null && v !== undefined && v !== "")
    .map(([k, v]) => `${k}: ${typeof v === "object" ? JSON.stringify(v) : String(v)}`)
    .join(" · ");
}

export default function AuditPage() {
  const { orgId, isAdmin } = useCurrentOrg();
  const events = useAuditEvents(orgId);
  const members = useOrgMembers(orgId);
  const emailById = new Map(members.data?.map((m) => [m.user.id, m.user.email]));

  if (!isAdmin) return <ErrorText>Only organization admins can view the audit log.</ErrorText>;

  return (
    <>
      <PageHeader
        title="Audit log"
        description="Who did what, and when. Entries cannot be edited."
      />
      <Card>
        {events.isPending ? (
          <Loading />
        ) : events.error ? (
          <ErrorText>{errorMessage(events.error)}</ErrorText>
        ) : (
          <table className="w-full text-sm">
            <thead className="text-muted text-left">
              <tr>
                <th className="pb-2 font-medium">When</th>
                <th className="pb-2 font-medium">Who</th>
                <th className="pb-2 font-medium">Action</th>
                <th className="pb-2 font-medium">Details</th>
              </tr>
            </thead>
            <tbody className="divide-border divide-y align-top">
              {events.data.map((e) => (
                <tr key={e.id}>
                  <td className="text-muted py-2 whitespace-nowrap">{formatDateTime(e.at)}</td>
                  <td className="py-2">
                    {(e.actor_user_id && emailById.get(e.actor_user_id)) ?? "—"}
                  </td>
                  <td className="py-2 font-mono text-xs">{e.action}</td>
                  <td className="text-muted py-2">{describe(e.data)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </>
  );
}
