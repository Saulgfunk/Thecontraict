"use client";

import { FolderOpen, Plus } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { DeadlineList } from "@/components/app/deadline-list";
import { useCurrentOrg } from "@/components/app/use-org";
import {
  Badge,
  Button,
  Card,
  ErrorText,
  Field,
  Input,
  Loading,
  PageHeader,
  Select,
} from "@/components/ui";
import { useCreateWorkspace, useDeadlines, useWorkspaces, type Schemas } from "@/lib/api";
import { DEFAULT_WORKSPACE_KIND, WORKSPACE_KIND_LABELS, WORKSPACE_ROLE_LABELS } from "@/lib/labels";
import { errorMessage } from "@/lib/utils";

function CreateWorkspaceForm({ onDone }: { onDone: () => void }) {
  const { orgId, org } = useCurrentOrg();
  const workspaces = useWorkspaces(orgId);
  const create = useCreateWorkspace(orgId);
  const [name, setName] = useState("");
  const [kind, setKind] = useState<Schemas["WorkspaceKind"]>(
    org ? DEFAULT_WORKSPACE_KIND[org.kind] : "client",
  );
  const [parent, setParent] = useState("");
  const [country, setCountry] = useState("");

  return (
    <form
      className="grid gap-4 sm:grid-cols-2"
      onSubmit={(e) => {
        e.preventDefault();
        create.mutate(
          {
            name,
            kind,
            parent_workspace_id: parent || null,
            country: country || null,
          },
          { onSuccess: onDone },
        );
      }}
    >
      <Field label="Name">
        <Input required autoFocus value={name} onChange={(e) => setName(e.target.value)} />
      </Field>
      <Field label="Type">
        <Select value={kind} onChange={(e) => setKind(e.target.value as Schemas["WorkspaceKind"])}>
          {Object.entries(WORKSPACE_KIND_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </Select>
      </Field>
      <Field label="Part of (optional)" hint="e.g. a subsidiary under its parent company">
        <Select value={parent} onChange={(e) => setParent(e.target.value)}>
          <option value="">—</option>
          {workspaces.data?.map((w) => (
            <option key={w.id} value={w.id}>
              {w.name}
            </option>
          ))}
        </Select>
      </Field>
      <Field label="Country (optional)" hint="Two-letter code; used for public holidays">
        <Input
          value={country}
          maxLength={2}
          onChange={(e) => setCountry(e.target.value.toUpperCase())}
        />
      </Field>
      <div className="flex items-center gap-3 sm:col-span-2">
        <Button type="submit" disabled={create.isPending}>
          {create.isPending ? "Creating…" : "Create workspace"}
        </Button>
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancel
        </Button>
        <ErrorText>{errorMessage(create.error)}</ErrorText>
      </div>
    </form>
  );
}

function UpcomingDeadlines({ orgId }: { orgId: string }) {
  const [in90] = useState(() => new Date(Date.now() + 90 * 86_400_000).toISOString().slice(0, 10));
  const deadlines = useDeadlines(orgId, { to: in90 });
  return (
    <Card
      title="Next 90 days"
      description="Notice, renewal and payment dates."
      actions={
        <Link href={`/app/${orgId}/deadlines`} className="text-primary text-sm hover:underline">
          All
        </Link>
      }
    >
      {deadlines.isPending ? (
        <Loading />
      ) : deadlines.error ? (
        <ErrorText>{errorMessage(deadlines.error)}</ErrorText>
      ) : deadlines.data.length === 0 ? (
        <p className="text-muted text-sm">
          Nothing due. Upload contracts to a workspace to see their deadlines here, or try the{" "}
          <Link
            href={`/app/${orgId}/tools/deadline-calculator`}
            className="text-primary hover:underline"
          >
            deadline calculator
          </Link>
          .
        </p>
      ) : (
        <DeadlineList orgId={orgId} items={deadlines.data.slice(0, 12)} compact />
      )}
    </Card>
  );
}

export default function DashboardPage() {
  const { orgId, org, isAdmin } = useCurrentOrg();
  const workspaces = useWorkspaces(orgId);
  const [creating, setCreating] = useState(false);
  const byId = new Map(workspaces.data?.map((w) => [w.id, w]));

  return (
    <>
      <PageHeader
        title={org?.name ?? "Dashboard"}
        description="Your workspaces and upcoming deadlines."
      />

      <div className="grid gap-6 lg:grid-cols-3">
        <Card
          className="lg:col-span-2"
          title="Workspaces"
          description="Each workspace keeps its contracts and team access separate."
          actions={
            isAdmin && !creating ? (
              <Button variant="secondary" onClick={() => setCreating(true)}>
                <Plus className="size-4" /> New
              </Button>
            ) : null
          }
        >
          {creating && (
            <div className="border-border mb-6 rounded-md border p-4">
              <CreateWorkspaceForm onDone={() => setCreating(false)} />
            </div>
          )}
          {workspaces.isPending ? (
            <Loading />
          ) : workspaces.error ? (
            <ErrorText>{errorMessage(workspaces.error)}</ErrorText>
          ) : workspaces.data.length === 0 ? (
            <p className="text-muted text-sm">
              {isAdmin
                ? "No workspaces yet. Create one for each client, entity or department."
                : "You haven't been added to any workspaces yet. Ask an admin for access."}
            </p>
          ) : (
            <ul className="divide-border divide-y">
              {workspaces.data.map((w) => (
                <li key={w.id}>
                  <Link
                    href={`/app/${orgId}/workspaces/${w.id}`}
                    className="hover:text-primary flex items-center justify-between gap-4 py-3"
                  >
                    <span className="flex items-center gap-3">
                      <FolderOpen className="text-muted size-4" />
                      <span>
                        <span className="font-medium">{w.name}</span>
                        {w.parent_workspace_id && byId.get(w.parent_workspace_id) && (
                          <span className="text-muted text-sm">
                            {" "}
                            · part of {byId.get(w.parent_workspace_id)?.name}
                          </span>
                        )}
                      </span>
                    </span>
                    <span className="flex gap-2">
                      <Badge>{WORKSPACE_KIND_LABELS[w.kind]}</Badge>
                      <Badge tone="primary">{WORKSPACE_ROLE_LABELS[w.my_role]}</Badge>
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <UpcomingDeadlines orgId={orgId} />
      </div>
    </>
  );
}
