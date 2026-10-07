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
          className="h-8 px-3 text-xs"
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
      className="border-border bg-surface fixed right-4 bottom-4 left-4 z-50 flex items-center justify-between gap-3 rounded-lg border p-3 text-sm shadow-lg sm:left-auto sm:w-96"
    >
      <span className="flex items-center gap-2">
        <Check className="text-success size-4 shrink-0" />
        {toast.message}
      </span>
      <span className="flex shrink-0 gap-1">
        <Button
          variant="ghost"
          className="h-8 px-2 text-xs"
          onClick={() => {
            toast.undo();
            setToast(null);
          }}
        >
          <Undo2 className="size-3.5" /> Undo
        </Button>
        <Button variant="ghost" className="h-8 px-2 text-xs" onClick={() => setToast(null)}>
          ✕
        </Button>
      </span>
    </div>
  ) : null;
  return { show, node };
}

/** A deadline as a row: sentence, contract, due date and the one-click choices. */
export function AttentionRow({
  orgId,
  deadline: d,
  onDone,
  compact = false,
}: {
  orgId: string;
  deadline: Schemas["DeadlineWithContract"];
  onDone: Done;
  /** Narrow column: no workspace name, date on its own line. */
  compact?: boolean;
}) {
  return (
    <li
      className={cn(
        "flex justify-between gap-3 py-3",
        compact ? "items-start" : "flex-wrap items-center",
      )}
    >
      <div className="min-w-0">
        <p className="font-medium">{deadlineSentence(d)}</p>
        <p className="text-sm">
          <Link
            href={`/app/${orgId}/contracts/${d.contract_id}`}
            className="text-primary hover:underline"
          >
            {d.contract_title}
          </Link>
          {compact ? <br /> : <span className="text-muted"> · {d.workspace_name} · </span>}
          <DueText date={d.due_date} />
          {!d.confirmed && (
            <span className="ml-2">
              <Badge tone="warning">Check this date</Badge>
            </span>
          )}
        </p>
      </div>
      <QuickActions orgId={orgId} deadline={d} onDone={onDone} />
    </li>
  );
}
