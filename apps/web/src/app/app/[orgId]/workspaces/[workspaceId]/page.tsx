"use client";

import { Trash2 } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";

import { ContractsPanel } from "@/components/app/contracts-panel";
import { useCurrentOrg } from "@/components/app/use-org";
import {
  Badge,
  Button,
  Card,
  ErrorText,
  Field,
  Loading,
  PageHeader,
  Select,
} from "@/components/ui";
import {
  useOrgMembers,
  useRemoveWorkspaceMember,
  useSetWorkspaceMember,
  useWorkspace,
  useWorkspaceMembers,
  type Schemas,
} from "@/lib/api";
import { WORKSPACE_KIND_LABELS, WORKSPACE_ROLE_LABELS } from "@/lib/labels";
import { errorMessage } from "@/lib/utils";

function AddMemberForm({ orgId, workspaceId }: { orgId: string; workspaceId: string }) {
  const orgMembers = useOrgMembers(orgId);
  const members = useWorkspaceMembers(orgId, workspaceId);
  const add = useSetWorkspaceMember(orgId, workspaceId);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Schemas["WorkspaceRole"]>("viewer");
  const existing = new Set(members.data?.map((m) => m.user.id));
  const candidates = orgMembers.data?.filter((m) => !existing.has(m.user.id)) ?? [];

  return (
    <form
      className="flex flex-wrap items-end gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        add.mutate({ email, role }, { onSuccess: () => setEmail("") });
      }}
    >
      <Field label="Organization member" className="min-w-56 flex-1">
        <Select required value={email} onChange={(e) => setEmail(e.target.value)}>
          <option value="">Select…</option>
          {candidates.map((m) => (
            <option key={m.id} value={m.user.email}>
              {m.user.name ? `${m.user.name} (${m.user.email})` : m.user.email}
            </option>
          ))}
        </Select>
      </Field>
      <Field label="Role">
        <Select value={role} onChange={(e) => setRole(e.target.value as Schemas["WorkspaceRole"])}>
          {Object.entries(WORKSPACE_ROLE_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </Select>
      </Field>
      <Button type="submit" disabled={add.isPending || !email}>
        Add
      </Button>
      <ErrorText>{errorMessage(add.error)}</ErrorText>
    </form>
  );
}

export default function WorkspacePage() {
  const { workspaceId } = useParams<{ workspaceId: string }>();
  const { orgId, me } = useCurrentOrg();
  const workspace = useWorkspace(orgId, workspaceId);
  const members = useWorkspaceMembers(orgId, workspaceId);
  const setMember = useSetWorkspaceMember(orgId, workspaceId);
  const remove = useRemoveWorkspaceMember(orgId, workspaceId);

  if (workspace.isPending) return <Loading />;
  if (workspace.error) return <ErrorText>{errorMessage(workspace.error)}</ErrorText>;
  const ws = workspace.data;
  const canManage = ws.my_role === "admin";

  return (
    <>
      <Link href={`/app/${orgId}`} className="text-muted text-sm hover:underline">
        ← Dashboard
      </Link>
      <PageHeader
        title={ws.name}
        description={[WORKSPACE_KIND_LABELS[ws.kind], ws.country].filter(Boolean).join(" · ")}
        actions={<Badge tone="primary">Your role: {WORKSPACE_ROLE_LABELS[ws.my_role]}</Badge>}
      />

      <div className="grid gap-6 lg:grid-cols-3">
        <Card
          className="lg:col-span-2"
          title="Contracts"
          description="Only members of this workspace and organization admins can see them."
        >
          <ContractsPanel
            orgId={orgId}
            workspaceId={workspaceId}
            canEdit={ws.my_role === "admin" || ws.my_role === "editor"}
          />
        </Card>

        <Card
          title="Members"
          description="Org owners and admins can always access every workspace."
        >
          {members.isPending ? (
            <Loading />
          ) : members.error ? (
            <ErrorText>{errorMessage(members.error)}</ErrorText>
          ) : members.data.length === 0 ? (
            <p className="text-muted text-sm">No members added yet.</p>
          ) : (
            <ul className="divide-border divide-y">
              {members.data.map((m) => (
                <li key={m.id} className="flex items-center justify-between gap-2 py-2 text-sm">
                  <span className="truncate" title={m.user.email}>
                    {m.user.name ?? m.user.email}
                    {m.user.id === me?.id && <span className="text-muted"> (you)</span>}
                  </span>
                  {canManage ? (
                    <span className="flex items-center gap-1">
                      <Select
                        aria-label="Role"
                        className="h-8 w-28"
                        value={m.role}
                        onChange={(e) =>
                          setMember.mutate({
                            email: m.user.email,
                            role: e.target.value as Schemas["WorkspaceRole"],
                          })
                        }
                      >
                        {Object.entries(WORKSPACE_ROLE_LABELS).map(([value, label]) => (
                          <option key={value} value={value}>
                            {label}
                          </option>
                        ))}
                      </Select>
                      <button
                        className="text-muted hover:text-danger rounded p-1.5"
                        aria-label={`Remove ${m.user.email}`}
                        onClick={() => remove.mutate(m.id)}
                      >
                        <Trash2 className="size-4" />
                      </button>
                    </span>
                  ) : (
                    <Badge>{WORKSPACE_ROLE_LABELS[m.role]}</Badge>
                  )}
                </li>
              ))}
            </ul>
          )}
          <ErrorText>{errorMessage(setMember.error || remove.error)}</ErrorText>
          {canManage && (
            <div className="border-border mt-4 border-t pt-4">
              <AddMemberForm orgId={orgId} workspaceId={workspaceId} />
            </div>
          )}
        </Card>
      </div>
    </>
  );
}
