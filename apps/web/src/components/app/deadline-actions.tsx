"use client";

import { Check, Undo2 } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { countdownText, daysUntil, formatIsoDate } from "@/components/app/contract-bits";
import { Badge, Button, ErrorText } from "@/components/ui";
import { useUpdateDeadline, type Schemas } from "@/lib/api";
import { DECISION_LABELS } from "@/lib/labels";
import { cn, errorMessage } from "@/lib/utils";

type Deadline = Schemas["DeadlineOut"] & {
  counterparty_name?: string | null;
  contract_title?: string;
};
type Decision = Schemas["DeadlineDecision"];

/** One plain-language sentence saying what the deadline means. */
export function deadlineSentence(d: Deadline): string {
  const to = d.counterparty_name ? ` to ${d.counterparty_name}` : "";
  switch (d.kind) {
    case "notice":
      return /renew/i.test(d.label)
        ? `Last day to tell ${d.counterparty_name ?? "the other party"} you don't want to renew`
        : `Last day to give ${lowerFirst(d.label)}${to}`;
    case "option":
      return `Last day to decide: ${d.label}`;
    case "term_end":
      return /renew/i.test(d.label) ? "Renews automatically" : "The contract ends";
    case "price_review":
      return `${d.label} due`;
    case "payment":
      return `${d.label.replace(/^payment:\s*/i, "")} due`;
    default:
      return d.label;
  }
}

function lowerFirst(s: string) {
  return /^[A-Z][a-z]/.test(s) ? s[0].toLowerCase() + s.slice(1) : s;
}

/** The one-click choices offered for each kind of deadline. */
function choices(kind: Schemas["DeadlineKind"]): { decision: Decision | null; label: string }[] {
  switch (kind) {
    case "notice":
    case "term_end":
      return [
        { decision: "renew", label: "Renew" },
        { decision: "terminate", label: "Cancel" },
        { decision: "renegotiate", label: "Renegotiate" },
      ];
    case "option":
      return [
        { decision: "exercise_option", label: "Use it" },
        { decision: "no_action", label: "Don't use it" },
      ];
    default:
      return [{ decision: null, label: "Done" }];
  }
}

export type Urgency = "overdue" | "soon" | "upcoming" | "later";

export function urgency(date: string): Urgency {
  const days = daysUntil(date);
  return days < 0 ? "overdue" : days <= 14 ? "soon" : days <= 45 ? "upcoming" : "later";
}

const TILE_TONE: Record<Urgency, string> = {
  overdue: "bg-danger/10 text-danger ring-danger/25",
  soon: "bg-warning/10 text-warning ring-warning/25",
  upcoming: "bg-primary/8 text-primary ring-primary/20",
  later: "bg-foreground/[0.04] text-muted ring-foreground/10",
};

/** A small calendar leaf: month above, day below, tinted by how close the date is. */
export function DateTile({ date, className }: { date: string; className?: string }) {
  const [y, m, d] = date.split("-").map(Number);
  const month = new Date(Date.UTC(y, m - 1, d)).toLocaleDateString(undefined, {
    month: "short",
    timeZone: "UTC",
  });
  return (
    <span
      className={cn(
        "flex size-12 shrink-0 flex-col items-center justify-center rounded-xl ring-1 ring-inset",
        TILE_TONE[urgency(date)],
        className,
      )}
      aria-hidden
    >
      <span className="text-[10px] leading-none font-semibold tracking-wider uppercase">
        {month}
      </span>
      <span className="mt-0.5 text-lg leading-none font-semibold">{d}</span>
    </span>
  );
}

export function DueText({ date, className }: { date: string; className?: string }) {
  const days = daysUntil(date);
  return (
    <span
      className={cn(
        "text-sm",
        days < 0
          ? "text-danger font-medium"
          : days <= 14
            ? "text-warning font-medium"
            : "text-muted",
        className,
      )}
    >
      {formatIsoDate(date)} · {countdownText(days)}
    </span>
  );
}

/**
 * Buttons that record what the user decided (nothing is sent to anyone). After a choice
 * the deadline is closed, so it leaves the "needs attention" lists; Undo reopens it.
 */
export function QuickActions({
  orgId,
  deadline: d,
  onDone,
}: {
  orgId: string;
  deadline: Deadline;
  onDone?: Done;
}) {
  const update = useUpdateDeadline(orgId);
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {choices(d.kind).map(({ decision, label }) => (
        <Button
          key={label}
          variant="secondary"
          className="h-8 rounded-full px-3.5 text-xs"
          disabled={update.isPending}
          onClick={async () => {
            // mutateAsync, not mutate: the row unmounts once the list refreshes without it,
            // and React Query skips per-call callbacks of unmounted components.
            try {
              await update.mutateAsync(
                decision ? { id: d.id, decision } : { id: d.id, status: "done" },
              );
            } catch {
              return; // shown below via update.error
            }
            onDone?.(
              decision
                ? `Recorded “${DECISION_LABELS[decision]}” for ${d.contract_title ?? d.label}.`
                : `Marked “${d.label}” as done.`,
              d.id,
            );
          }}
        >
          {label}
        </Button>
      ))}
      <ErrorText>{errorMessage(update.error)}</ErrorText>
    </div>
  );
}

type Done = (message: string, deadlineId: string) => void;

/** A short confirmation with an Undo button, shown after a quick action. */
export function useUndoToast(orgId: string) {
  const update = useUpdateDeadline(orgId);
  const [toast, setToast] = useState<{ message: string; undo: () => void } | null>(null);
  const show: Done = (message, id) =>
    setToast({ message, undo: () => update.mutate({ id, decision: null, status: "open" }) });
  const node = toast ? (
    <div
      role="status"
      className="bg-sidebar text-sidebar-foreground animate-rise fixed right-4 bottom-4 left-4 z-50 flex items-center justify-between gap-3 rounded-xl p-3 pl-4 text-sm shadow-(--shadow-raised) sm:left-auto sm:w-[26rem]"
    >
      <span className="flex items-center gap-2">
        <Check className="size-4 shrink-0 text-[#6fe0a0]" />
        {toast.message}
      </span>
      <span className="flex shrink-0 gap-1">
        <Button
          variant="ghost"
          className="h-8 px-2 text-xs text-white hover:bg-white/10"
          onClick={() => {
            toast.undo();
            setToast(null);
          }}
        >
          <Undo2 className="size-3.5" /> Undo
        </Button>
        <Button
          variant="ghost"
          aria-label="Close"
          className="text-sidebar-muted h-8 px-2 text-xs hover:bg-white/10 hover:text-white"
          onClick={() => setToast(null)}
        >
          ✕
        </Button>
      </span>
    </div>
  ) : null;
  return { show, node };
}

/** A deadline as a row: date tile, sentence, contract, and the one-click choices. */
export function AttentionRow({
  orgId,
  deadline: d,
  onDone,
  compact = false,
}: {
  orgId: string;
  deadline: Schemas["DeadlineWithContract"];
  onDone: Done;
  /** Narrow column: no workspace name, actions below. */
  compact?: boolean;
}) {
  return (
    <li
      className={cn(
        "hover:bg-foreground/[0.025] -mx-3 flex gap-4 rounded-xl px-3 py-3.5 transition-colors",
        compact ? "items-start" : "flex-wrap items-center sm:flex-nowrap",
      )}
    >
      <DateTile date={d.due_date} className={compact ? "size-11" : undefined} />
      <div className="min-w-0 flex-1">
        <p className="leading-snug font-medium">{deadlineSentence(d)}</p>
        <p className="mt-0.5 text-sm">
          <Link
            href={`/app/${orgId}/contracts/${d.contract_id}`}
            className="text-foreground/80 hover:text-primary underline decoration-current/20 underline-offset-2"
          >
            {d.contract_title}
          </Link>
          {!compact && <span className="text-muted"> · {d.workspace_name}</span>}
        </p>
        <p className="mt-0.5 flex flex-wrap items-center gap-2">
          <DueText date={d.due_date} className="text-xs" />
          {!d.confirmed && <Badge tone="warning">Check this date</Badge>}
        </p>
        {compact && (
          <div className="mt-2">
            <QuickActions orgId={orgId} deadline={d} onDone={onDone} />
          </div>
        )}
      </div>
      {!compact && (
        <div className="w-full pl-16 sm:w-auto sm:shrink-0 sm:pl-0">
          <QuickActions orgId={orgId} deadline={d} onDone={onDone} />
        </div>
      )}
    </li>
  );
}
