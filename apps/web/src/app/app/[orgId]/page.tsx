"use client";

import {
  AlertTriangle,
  BellRing,
  CalendarClock,
  CheckCircle2,
  FilePlus2,
  FileText,
  FolderPlus,
  Wallet,
} from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { AttentionRow, useUndoToast } from "@/components/app/deadline-actions";
import { useCurrentOrg } from "@/components/app/use-org";
import { AddContractButton, CreateWorkspaceForm } from "@/components/app/workspace-bits";
import { Card, ErrorText, Loading, PageHeader } from "@/components/ui";
import { useAllContracts, useDeadlines, useWorkspaces, type Schemas } from "@/lib/api";
import { WORKSPACE_NOUN } from "@/lib/labels";
import { cn, errorMessage } from "@/lib/utils";

type Item = Schemas["DeadlineWithContract"];

const isoInDays = (days: number) =>
  new Date(Date.now() + days * 86_400_000).toISOString().slice(0, 10);

const SECTION_DOT = { danger: "bg-danger", warning: "bg-warning", primary: "bg-primary" };

function Section({
  title,
  tone,
  items,
  onDone,
}: {
  title: string;
  tone: keyof typeof SECTION_DOT;
  items: Item[];
  onDone: (message: string, deadlineId: string) => void;
}) {
  const { orgId } = useCurrentOrg();
  if (items.length === 0) return null;
  return (
    <section>
      <h2 className="text-muted mb-1 flex items-center gap-2 text-xs font-semibold tracking-[0.1em] uppercase">
        <span className={cn("size-1.5 rounded-full", SECTION_DOT[tone])} />
        {title}
        <span className="bg-foreground/5 rounded-full px-1.5 py-px text-[11px] tracking-normal">
          {items.length}
        </span>
      </h2>
      <ul>
        {items.map((d) => (
          <AttentionRow key={d.id} orgId={orgId} deadline={d} onDone={onDone} />
        ))}
      </ul>
    </section>
  );
}

const STAT_TONE = {
  danger: "text-danger bg-danger/10",
  warning: "text-warning bg-warning/10",
  primary: "text-primary bg-primary/10",
  accent: "text-accent bg-accent/15",
};

function Stat({
  label,
  value,
  icon: Icon,
  tone,
  note,
}: {
  label: string;
  value: number;
  icon: typeof FileText;
  tone: keyof typeof STAT_TONE;
  note?: string;
}) {
  return (
    <div className="border-border/80 bg-surface animate-rise rounded-2xl border p-5 shadow-(--shadow-card)">
      <div className="flex items-center justify-between gap-2">
        <p className="text-muted text-sm">{label}</p>
        <span className={cn("rounded-lg p-1.5", STAT_TONE[tone])}>
          <Icon className="size-4" />
        </span>
      </div>
      <p className="mt-3 text-3xl font-semibold tracking-tight">{value}</p>
      {note && <p className="text-muted mt-1 text-xs">{note}</p>}
    </div>
  );
}

function greeting() {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
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
      eyebrow={greeting()}
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

  const overdueAll = deadlines.data.filter((d) => d.due_date < today);

  return (
    <>
      {header}
      <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Stat
          label="Overdue"
          value={overdueAll.length}
          icon={AlertTriangle}
          tone="danger"
          note={overdueAll.length ? "Past their date and still open" : "Nothing overdue"}
        />
        <Stat
          label="To decide in 30 days"
          value={soon.length + overdue.length}
          icon={CalendarClock}
          tone="warning"
          note="Notice, renewal and option dates"
        />
        <Stat
          label="Payments in 30 days"
          value={payments.length}
          icon={Wallet}
          tone="primary"
          note="Invoices to pay or send"
        />
        <Stat
          label="Contracts tracked"
          value={contracts.data.length}
          icon={FileText}
          tone="accent"
          note="Reminders on for all of them"
        />
      </div>
      <div className="grid gap-6 xl:grid-cols-3">
        <Card className="xl:col-span-2" title="Dates that need a decision">
          {actions.length === 0 ? (
            <div className="flex flex-col items-center gap-2 py-10 text-center">
              <span className="bg-success/10 text-success rounded-full p-3">
                <CheckCircle2 className="size-6" />
              </span>
              <p className="font-medium">All clear</p>
              <p className="text-muted text-sm">
                No notice, renewal or option dates in the next 90 days.
              </p>
            </div>
          ) : (
            <div className="space-y-6">
              <Section title="Overdue" tone="danger" items={overdue} onDone={toast.show} />
              <Section title="Next 30 days" tone="warning" items={soon} onDone={toast.show} />
              <Section title="In 1 to 3 months" tone="primary" items={later} onDone={toast.show} />
            </div>
          )}
          <p className="border-border text-muted mt-5 border-t pt-4 text-sm">
            <Link
              href={`/app/${orgId}/deadlines`}
              className="text-primary font-medium hover:underline"
            >
              See all dates
            </Link>{" "}
            in a list or calendar.
          </p>
        </Card>
        <Card title="Payments in the next 30 days">
          {payments.length === 0 ? (
            <p className="text-muted text-sm">None.</p>
          ) : (
            <ul>
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
