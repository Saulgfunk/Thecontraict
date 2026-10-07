"use client";

import { useState } from "react";

import { DeadlineList } from "@/components/app/deadline-list";
import { useCurrentOrg } from "@/components/app/use-org";
import { Card, ErrorText, Field, Loading, PageHeader, Select } from "@/components/ui";
import { useDeadlines, useWorkspaces, type Schemas } from "@/lib/api";
import { DEADLINE_KIND_LABELS } from "@/lib/labels";
import { errorMessage } from "@/lib/utils";

function isoDaysFromNow(days: number) {
  const d = new Date();
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}

export default function DeadlinesPage() {
  const { orgId } = useCurrentOrg();
  const workspaces = useWorkspaces(orgId);
  const [workspaceId, setWorkspaceId] = useState("");
  const [kind, setKind] = useState<Schemas["DeadlineKind"] | "">("");
  const [horizon, setHorizon] = useState("365");
  const [includeClosed, setIncludeClosed] = useState(false);
  const [to, setTo] = useState(() => isoDaysFromNow(365));
  const deadlines = useDeadlines(orgId, {
    workspace_id: workspaceId || undefined,
    to: to || undefined,
    include_closed: includeClosed,
  });
  const items = (deadlines.data ?? []).filter((d) => !kind || d.kind === kind);

  return (
    <>
      <PageHeader
        title="Deadlines"
        description="Every notice, renewal and payment date across the workspaces you can access."
      />
      <Card>
        <div className="mb-5 grid gap-3 sm:grid-cols-4">
          <Field label="Workspace">
            <Select value={workspaceId} onChange={(e) => setWorkspaceId(e.target.value)}>
              <option value="">All</option>
              {workspaces.data?.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.name}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Type">
            <Select
              value={kind}
              onChange={(e) => setKind(e.target.value as Schemas["DeadlineKind"] | "")}
            >
              <option value="">All</option>
              {Object.entries(DEADLINE_KIND_LABELS).map(([v, l]) => (
                <option key={v} value={v}>
                  {l}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Up to">
            <Select
              value={horizon}
              onChange={(e) => {
                setHorizon(e.target.value);
                setTo(e.target.value ? isoDaysFromNow(Number(e.target.value)) : "");
              }}
            >
              <option value="30">30 days</option>
              <option value="90">3 months</option>
              <option value="180">6 months</option>
              <option value="365">12 months</option>
              <option value="">Everything</option>
            </Select>
          </Field>
          <Field label="Show">
            <Select
              value={includeClosed ? "all" : "open"}
              onChange={(e) => setIncludeClosed(e.target.value === "all")}
            >
              <option value="open">Open only</option>
              <option value="all">Including done</option>
            </Select>
          </Field>
        </div>
        {deadlines.isPending ? (
          <Loading />
        ) : deadlines.error ? (
          <ErrorText>{errorMessage(deadlines.error)}</ErrorText>
        ) : items.length === 0 ? (
          <p className="text-muted text-sm">Nothing due in this period.</p>
        ) : (
          <DeadlineList orgId={orgId} items={items} grouped />
        )}
      </Card>
    </>
  );
}
