"use client";

import { FolderOpen, Plus, Search } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { ContractsPanel } from "@/components/app/contracts-panel";
import { useCurrentOrg } from "@/components/app/use-org";
import { AddContractButton, CreateWorkspaceForm } from "@/components/app/workspace-bits";
import { Button, Card, ErrorText, Input, Loading, PageHeader, Select } from "@/components/ui";
import { useWorkspaces } from "@/lib/api";
import { WORKSPACE_NOUN } from "@/lib/labels";
import { errorMessage } from "@/lib/utils";

const capitalize = (s: string) => s[0].toUpperCase() + s.slice(1);

export default function ContractsPage() {
  const { orgId, org, isAdmin } = useCurrentOrg();
  const workspaces = useWorkspaces(orgId);
  const [workspaceId, setWorkspaceId] = useState("");
  const [search, setSearch] = useState("");
  const [adding, setAdding] = useState(false);
  const noun = org ? WORKSPACE_NOUN[org.kind] : { one: "workspace", many: "workspaces" };
  const many = (workspaces.data?.length ?? 0) > 1;

  return (
    <>
      <PageHeader title="Contracts" actions={<AddContractButton />} />
      <div className="grid gap-6 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <div className="mb-4 flex flex-wrap gap-3">
            <label className="relative min-w-56 flex-1">
              <Search className="text-muted pointer-events-none absolute top-2.5 left-3 size-4" />
              <Input
                aria-label="Search contracts"
                placeholder="Search by name or other party"
                className="pl-9"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </label>
            {many && (
              <Select
                aria-label={`Filter by ${noun.one}`}
                className="w-auto"
                value={workspaceId}
                onChange={(e) => setWorkspaceId(e.target.value)}
              >
                <option value="">All {noun.many}</option>
                {workspaces.data?.map((w) => (
                  <option key={w.id} value={w.id}>
                    {w.name}
                  </option>
                ))}
              </Select>
            )}
          </div>
          <ContractsPanel
            orgId={orgId}
            workspaceId={workspaceId || undefined}
            canEdit={false}
            search={search}
          />
        </Card>

        <Card
          title={capitalize(noun.many)}
          description={`Each ${noun.one} keeps its contracts and team access separate. Open one to upload files or manage who can see it.`}
          actions={
            isAdmin && !adding ? (
              <Button variant="secondary" onClick={() => setAdding(true)}>
                <Plus className="size-4" /> Add
              </Button>
            ) : null
          }
        >
          {adding && (
            <div className="border-border mb-4 rounded-md border p-4">
              <CreateWorkspaceForm onDone={() => setAdding(false)} />
            </div>
          )}
          {workspaces.isPending ? (
            <Loading />
          ) : workspaces.error ? (
            <ErrorText>{errorMessage(workspaces.error)}</ErrorText>
          ) : workspaces.data.length === 0 ? (
            <p className="text-muted text-sm">
              {isAdmin
                ? `Add your first ${noun.one} to start adding contracts.`
                : `You haven't been given access to any ${noun.many} yet. Ask an admin.`}
            </p>
          ) : (
            <ul className="divide-border divide-y">
              {workspaces.data.map((w) => (
                <li key={w.id}>
                  <Link
                    href={`/app/${orgId}/workspaces/${w.id}`}
                    className="hover:text-primary flex items-center gap-3 py-2.5 text-sm"
                  >
                    <FolderOpen className="text-muted size-4 shrink-0" />
                    <span className="truncate">{w.name}</span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </>
  );
}
