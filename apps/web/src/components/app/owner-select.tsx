"use client";

import { Select } from "@/components/ui";
import { useOrgMembers, useUpdateContract, useWorkspaceMembers, type Schemas } from "@/lib/api";
import { errorMessage } from "@/lib/utils";

/** Who receives this contract's reminders: workspace members and org admins. */
export function OwnerSelect({
  orgId,
  contract,
  canEdit,
}: {
  orgId: string;
  contract: Schemas["ContractDetail"];
  canEdit: boolean;
}) {
  const orgMembers = useOrgMembers(orgId);
  const wsMembers = useWorkspaceMembers(orgId, contract.workspace_id);
  const update = useUpdateContract(orgId, contract.id);
  const wsUserIds = new Set(wsMembers.data?.map((m) => m.user.id));
  const candidates = (orgMembers.data ?? []).filter(
    (m) => m.role === "owner" || m.role === "admin" || wsUserIds.has(m.user.id),
  );
  const label = (m: (typeof candidates)[number]) => m.user.name ?? m.user.email;

  return (
    <label
      className="text-muted flex items-center gap-2 text-sm"
      title={errorMessage(update.error)}
    >
      Reminders to
      <Select
        aria-label="Reminders go to"
        className="h-9 w-48"
        disabled={!canEdit || update.isPending}
        value={contract.owner_id ?? ""}
        onChange={(e) => update.mutate({ owner_id: e.target.value || null })}
      >
        <option value="">Workspace admins</option>
        {candidates.map((m) => (
          <option key={m.user.id} value={m.user.id}>
            {label(m)}
          </option>
        ))}
      </Select>
    </label>
  );
}
