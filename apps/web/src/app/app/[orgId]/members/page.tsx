"use client";

import { Trash2 } from "lucide-react";
import { useState } from "react";

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
import {
  useAddOrgMember,
  useOrgMembers,
  useRemoveOrgMember,
  useUpdateOrgMember,
  type Schemas,
} from "@/lib/api";
import { ORG_ROLE_LABELS } from "@/lib/labels";
import { errorMessage, formatDate } from "@/lib/utils";

export default function MembersPage() {
  const { orgId, isAdmin, isOwner, me } = useCurrentOrg();
  const members = useOrgMembers(orgId);
  const add = useAddOrgMember(orgId);
  const update = useUpdateOrgMember(orgId);
  const remove = useRemoveOrgMember(orgId);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Schemas["OrgRole"]>("member");
  const assignableRoles = Object.entries(ORG_ROLE_LABELS).filter(
    ([value]) => isOwner || value !== "owner",
  );

  return (
    <>
      <PageHeader
        title="Members"
        description="People in this organization. Members only see the workspaces they are added to."
      />
      <div className="space-y-6">
        {isAdmin && (
          <Card
            title="Invite someone"
            description="They get access when they sign in with this email."
          >
            <form
              className="flex flex-wrap items-end gap-3"
              onSubmit={(e) => {
                e.preventDefault();
                add.mutate({ email, role }, { onSuccess: () => setEmail("") });
              }}
            >
              <Field label="Email" className="min-w-64 flex-1">
                <Input
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </Field>
              <Field label="Role">
                <Select
                  value={role}
                  onChange={(e) => setRole(e.target.value as Schemas["OrgRole"])}
                >
                  {assignableRoles.map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </Select>
              </Field>
              <Button type="submit" disabled={add.isPending}>
                Invite
              </Button>
              <ErrorText>{errorMessage(add.error)}</ErrorText>
            </form>
          </Card>
        )}

        <Card>
          {members.isPending ? (
            <Loading />
          ) : members.error ? (
            <ErrorText>{errorMessage(members.error)}</ErrorText>
          ) : (
            <table className="w-full text-sm">
              <thead className="text-muted text-left">
                <tr>
                  <th className="pb-2 font-medium">Name</th>
                  <th className="pb-2 font-medium">Email</th>
                  <th className="pb-2 font-medium">Role</th>
                  <th className="pb-2 font-medium">Added</th>
                  <th />
                </tr>
              </thead>
              <tbody className="divide-border divide-y">
                {members.data.map((m) => {
                  const editable = isAdmin && (isOwner || m.role !== "owner");
                  return (
                    <tr key={m.id}>
                      <td className="py-2">
                        {m.user.name ?? <span className="text-muted">Invited</span>}
                        {m.user.id === me?.id && <span className="text-muted"> (you)</span>}
                      </td>
                      <td className="py-2">{m.user.email}</td>
                      <td className="py-2">
                        {editable ? (
                          <Select
                            aria-label="Role"
                            className="h-8 w-32"
                            value={m.role}
                            onChange={(e) =>
                              update.mutate({
                                memberId: m.id,
                                role: e.target.value as Schemas["OrgRole"],
                              })
                            }
                          >
                            {assignableRoles.map(([value, label]) => (
                              <option key={value} value={value}>
                                {label}
                              </option>
                            ))}
                          </Select>
                        ) : (
                          <Badge>{ORG_ROLE_LABELS[m.role]}</Badge>
                        )}
                      </td>
                      <td className="text-muted py-2">{formatDate(m.created_at)}</td>
                      <td className="py-2 text-right">
                        {(editable || m.user.id === me?.id) && (
                          <button
                            className="text-muted hover:text-danger rounded p-1.5"
                            aria-label={
                              m.user.id === me?.id ? "Leave organization" : `Remove ${m.user.email}`
                            }
                            title={m.user.id === me?.id ? "Leave organization" : "Remove"}
                            onClick={() => remove.mutate(m.id)}
                          >
                            <Trash2 className="size-4" />
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
          <ErrorText>{errorMessage(update.error || remove.error)}</ErrorText>
        </Card>
      </div>
    </>
  );
}
