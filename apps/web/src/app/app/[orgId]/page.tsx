"use client";

import { BellRing, CheckCircle2, FilePlus2, FolderPlus } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { AttentionRow, useUndoToast } from "@/components/app/deadline-actions";
import { useCurrentOrg } from "@/components/app/use-org";
import { AddContractButton, CreateWorkspaceForm } from "@/components/app/workspace-bits";
import { Card, ErrorText, Loading, PageHeader } from "@/components/ui";
import { useAllContracts, useDeadlines, useWorkspaces, type Schemas } from "@/lib/api";
import { WORKSPACE_NOUN } from "@/lib/labels";
import { errorMessage } from "@/lib/utils";

type Item = Schemas["DeadlineWithContract"];

const isoInDays = (days: number) =>
  new Date(Date.now() + days * 86_400_000).toISOString().slice(0, 10);

function Section({
  title,
  tone,
  items,
  onDone,
}: {
  title: string;
  tone?: "danger";
  items: Item[];
  onDone: (message: string, deadlineId: string) => void;
}) {
  const { orgId } = useCurrentOrg();
  if (items.length === 0) return null;
  return (
    <section>
      <h2 className={tone === "danger" ? "text-danger font-semibold" : "font-semibold"}>
        {title} <span className="text-muted font-normal">({items.length})</span>
      </h2>
      <ul className="divide-border divide-y">
        {items.map((d) => (
          <AttentionRow key={d.id} orgId={orgId} deadline={d} onDone={onDone} />
        ))}
      </ul>
    </section>
  );
}

function GetStarted() {
  const { orgId, org, isAdmin } = useCurrentOrg();
  const workspaces = useWorkspaces(orgId);
  const [adding, setAdding] = useState(false);
  const noun = org ? WORKSPACE_NOUN[org.kind] : { one: "workspace", many: "workspaces" };
  const hasWorkspace = (workspaces.data?.length ?? 0) > 0;

  const steps = [
    {
      icon: FolderPlus,
      title: `Add your first ${noun.one}`,
      text: `Contracts are kept per ${noun.one}, so each team only sees its own.`,
      done: hasWorkspace,
      action: isAdmin && !hasWorkspace && !adding && (
        <button
          className="text-primary text-sm font-medium hover:underline"
          onClick={() => setAdding(true)}
        >
          Add {noun.one}
        </button>
      ),
    },
    {
      icon: FilePlus2,
      title: "Add a contract",
      text: "Type in the end date and notice period, or upload the signed copy.",
      done: false,
      action: hasWorkspace && <AddContractButton />,
    },
    {
      icon: BellRing,
      title: "Get reminded",
      text: "Reminders are on automatically: by email and here in the app, starting four months before a notice deadline. You can change the timing in Settings.",
      done: false,
      action: null,
    },
  ];

  return (
    <Card title="Get started" description="Three steps, a couple of minutes.">
      <ol className="space-y-5">
        {steps.map(({ icon: Icon, title, text, done, action }, i) => (
          <li key={title} className="flex gap-4">
            <span className="bg-primary/10 text-primary flex size-9 shrink-0 items-center justify-center rounded-full">
              {done ? <CheckCircle2 className="size-5" /> : <Icon className="size-5" />}
            </span>
            <div className="min-w-0 flex-1 space-y-2">
              <p className={done ? "text-muted font-medium line-through" : "font-medium"}>
                {i + 1}. {title}
              </p>
              <p className="text-muted text-sm">{text}</p>
              {action}
              {i === 0 && adding && <CreateWorkspaceForm onDone={() => setAdding(false)} />}
            </div>
          </li>
        ))}
      </ol>
    </Card>
  );
}

export default function HomePage() {
  const { orgId } = useCurrentOrg();
  const [to] = useState(() => isoInDays(90));
  const [today] = useState(() => isoInDays(0));
  const [in30] = useState(() => isoInDays(30));
  const deadlines = useDeadlines(orgId, { to });
  const contracts = useAllContracts(orgId);
  const toast = useUndoToast(orgId);

  const header = (
    <PageHeader
      title="What needs your attention"
      description="Choosing Renew, Cancel or another option only records your decision. Nothing is sent to anyone."
      actions={<AddContractButton />}
    />
  );

  if (deadlines.isPending || contracts.isPending)
    return (
      <>
        {header}
        <Loading />
      </>
    );
  const error = deadlines.error || contracts.error;
  if (error)
    return (
      <>
        {header}
        <ErrorText>{errorMessage(error)}</ErrorText>
      </>
    );

  if (contracts.data.length === 0) {
    return (
      <>
        {header}
        <div className="max-w-2xl">
          <GetStarted />
        </div>
      </>
    );
  }

  const actions = deadlines.data.filter((d) => d.kind !== "payment");
  const payments = deadlines.data.filter((d) => d.kind === "payment" && d.due_date <= in30);
  const overdue = actions.filter((d) => d.due_date < today);
  const soon = actions.filter((d) => d.due_date >= today && d.due_date <= in30);
  const later = actions.filter((d) => d.due_date > in30);

  return (
    <>
      {header}
      <div className="grid gap-6 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          {actions.length === 0 ? (
            <p className="flex items-center gap-2 text-sm">
              <CheckCircle2 className="text-success size-5" />
              All clear: no notice, renewal or option dates in the next 90 days.
            </p>
          ) : (
            <div className="space-y-6">
              <Section title="Overdue" tone="danger" items={overdue} onDone={toast.show} />
              <Section title="Next 30 days" items={soon} onDone={toast.show} />
              <Section title="In 1 to 3 months" items={later} onDone={toast.show} />
            </div>
          )}
          <p className="text-muted mt-4 text-sm">
            <Link href={`/app/${orgId}/deadlines`} className="text-primary hover:underline">
              See all dates
            </Link>{" "}
            in a list or calendar.
          </p>
        </Card>
        <Card title="Payments in the next 30 days">
          {payments.length === 0 ? (
            <p className="text-muted text-sm">None.</p>
          ) : (
            <ul className="divide-border divide-y">
              {payments.map((d) => (
                <AttentionRow key={d.id} orgId={orgId} deadline={d} onDone={toast.show} compact />
              ))}
            </ul>
          )}
        </Card>
      </div>
      {toast.node}
    </>
  );
}
