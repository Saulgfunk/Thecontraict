"use client";

import { ChevronDown, Plus } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { useCurrentOrg } from "@/components/app/use-org";
import { Button, ErrorText, Field, Input, Select } from "@/components/ui";
import { useCreateWorkspace, useWorkspaces, type Schemas } from "@/lib/api";
import { DEFAULT_WORKSPACE_KIND, WORKSPACE_KIND_LABELS, WORKSPACE_NOUN } from "@/lib/labels";
import { errorMessage } from "@/lib/utils";

const primaryLink =
  "bg-primary text-primary-foreground inline-flex h-9 items-center gap-2 rounded-md px-4 text-sm font-medium hover:opacity-90";

/** "Add contract": straight to the form when there's one place to put it, else a menu. */
export function AddContractButton() {
  const { orgId, org } = useCurrentOrg();
  const workspaces = useWorkspaces(orgId);
  const [open, setOpen] = useState(false);
  const editable =
    workspaces.data?.filter((w) => w.my_role === "admin" || w.my_role === "editor") ?? [];
  if (editable.length === 0) return null;
  if (editable.length === 1) {
    return (
      <Link
        href={`/app/${orgId}/workspaces/${editable[0].id}/contracts/new`}
        className={primaryLink}
      >
        <Plus className="size-4" /> Add contract
      </Link>
    );
  }
  const noun = org ? WORKSPACE_NOUN[org.kind].one : "workspace";
  return (
    <div className="relative">
      <button className={primaryLink} onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        <Plus className="size-4" /> Add contract <ChevronDown className="size-4" />
      </button>
      {open && (
        <div className="border-border bg-surface absolute right-0 z-20 mt-1 w-64 rounded-md border p-1 shadow-lg">
          <p className="text-muted px-3 py-1.5 text-xs">Which {noun} is it for?</p>
          {editable.map((w) => (
            <Link
              key={w.id}
              href={`/app/${orgId}/workspaces/${w.id}/contracts/new`}
              className="hover:bg-background block truncate rounded px-3 py-2 text-sm"
            >
              {w.name}
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

export function CreateWorkspaceForm({ onDone }: { onDone: () => void }) {
  const { orgId, org } = useCurrentOrg();
  const workspaces = useWorkspaces(orgId);
  const create = useCreateWorkspace(orgId);
  const [name, setName] = useState("");
  const [kind, setKind] = useState<Schemas["WorkspaceKind"]>(
    org ? DEFAULT_WORKSPACE_KIND[org.kind] : "client",
  );
  const [parent, setParent] = useState("");
  const [country, setCountry] = useState("");
  const [more, setMore] = useState(false);
  const noun = org ? WORKSPACE_NOUN[org.kind].one : "workspace";

  return (
    <form
      className="grid gap-4 sm:grid-cols-2"
      onSubmit={(e) => {
        e.preventDefault();
        create.mutate(
          { name, kind, parent_workspace_id: parent || null, country: country || null },
          { onSuccess: onDone },
        );
      }}
    >
      <Field label={`Name of the ${noun}`} className="sm:col-span-2">
        <Input required autoFocus value={name} onChange={(e) => setName(e.target.value)} />
      </Field>
      {more ? (
        <>
          <Field label="Type">
            <Select
              value={kind}
              onChange={(e) => setKind(e.target.value as Schemas["WorkspaceKind"])}
            >
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
        </>
      ) : (
        <button
          type="button"
          className="text-primary justify-self-start text-sm hover:underline sm:col-span-2"
          onClick={() => setMore(true)}
        >
          More options
        </button>
      )}
      <div className="flex items-center gap-3 sm:col-span-2">
        <Button type="submit" disabled={create.isPending}>
          {create.isPending ? "Adding…" : `Add ${noun}`}
        </Button>
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancel
        </Button>
        <ErrorText>{errorMessage(create.error)}</ErrorText>
      </div>
    </form>
  );
}
