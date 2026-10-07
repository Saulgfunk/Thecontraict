"use client";

import {
  describeRule,
  formatIsoDate,
  formatMoney,
  formatPeriod,
} from "@/components/app/contract-bits";
import {
  DateTile,
  DueText,
  QuickActions,
  deadlineSentence,
  useUndoToast,
} from "@/components/app/deadline-actions";
import { Mail, X } from "lucide-react";
import { useState } from "react";

import { Badge, Button, Card, ErrorText, Input } from "@/components/ui";
import { useUpdateContract, type Schemas } from "@/lib/api";
import { DECISION_LABELS, FREQUENCY_LABELS } from "@/lib/labels";
import { errorMessage } from "@/lib/utils";

type Contract = Schemas["ContractDetail"];

/** The contract's length and renewal, as one sentence. */
export function termSentence(c: Contract): string | null {
  const parts: string[] = [];
  if (c.effective_date) parts.push(`Started ${formatIsoDate(c.effective_date)}`);
  if (c.initial_term_amount && c.initial_term_unit) {
    parts.push(
      `${parts.length ? "first term" : "First term"} ${formatPeriod(c.initial_term_amount, c.initial_term_unit)}`,
    );
  } else if (c.end_date) {
    parts.push(`${parts.length ? "ends" : "Ends"} ${formatIsoDate(c.end_date)}`);
  }
  if (c.auto_renews === true) {
    parts.push(
      c.renewal_term_amount && c.renewal_term_unit
        ? `then renews automatically for ${formatPeriod(c.renewal_term_amount, c.renewal_term_unit)} at a time`
        : "then renews automatically",
    );
  } else if (c.auto_renews === false) {
    parts.push("does not renew automatically");
  }
  return parts.length ? parts.join(", ") + "." : null;
}

/** Extra people (no account needed) who get the same reminder emails as the owner. */
function AlsoRemind({
  orgId,
  contract: c,
  canEdit,
}: {
  orgId: string;
  contract: Contract;
  canEdit: boolean;
}) {
  const update = useUpdateContract(orgId, c.id);
  const [draft, setDraft] = useState("");
  const emails = c.reminder_emails ?? [];
  const save = (next: string[], onSuccess?: () => void) =>
    update.mutate({ reminder_emails: next }, { onSuccess });

  return (
    <div className="space-y-2">
      {emails.length > 0 ? (
        <ul className="flex flex-wrap gap-1.5">
          {emails.map((address) => (
            <li
              key={address}
              className="bg-foreground/5 inline-flex items-center gap-1.5 rounded-full py-1 pr-1.5 pl-3 text-xs"
            >
              <Mail className="text-muted size-3" />
              {address}
              {canEdit && (
                <button
                  aria-label={`Stop reminding ${address}`}
                  className="text-muted hover:text-danger rounded-full p-0.5"
                  disabled={update.isPending}
                  onClick={() => save(emails.filter((e) => e !== address))}
                >
                  <X className="size-3" />
                </button>
              )}
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-muted">Only the owner is reminded.</p>
      )}
      {canEdit && (
        <form
          className="flex max-w-md gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            const address = draft.trim();
            if (address) save([...emails, address], () => setDraft(""));
          }}
        >
          <Input
            type="email"
            aria-label="Also remind (email)"
            placeholder="e.g. finance@yourcompany.com"
            className="h-9"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
          />
          <Button type="submit" variant="secondary" disabled={update.isPending || !draft.trim()}>
            Add
          </Button>
        </form>
      )}
      {canEdit && (
        <p className="text-muted text-xs">
          They get the reminder emails without needing an account. Useful for finance or outside
          counsel.
        </p>
      )}
      <ErrorText>{errorMessage(update.error)}</ErrorText>
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid gap-1 py-3.5 sm:grid-cols-[8rem_1fr] sm:gap-4">
      <dt className="text-muted text-xs font-semibold tracking-[0.08em] uppercase sm:pt-0.5">
        {label}
      </dt>
      <dd className="min-w-0 text-sm">{children}</dd>
    </div>
  );
}

export function ContractOverview({
  orgId,
  contract: c,
  canEdit,
  onReview,
}: {
  orgId: string;
  contract: Contract;
  canEdit: boolean;
  onReview: () => void;
}) {
  const toast = useUndoToast(orgId);
  const today = new Date().toISOString().slice(0, 10);
  const upcoming = c.deadlines.filter((d) => d.due_date >= today);
  const next = upcoming.find((d) => d.kind !== "payment" && d.status === "open");
  const lastDecided = c.deadlines.find(
    (d) => d.kind !== "payment" && d.decision && d.due_date >= today,
  );
  const nextPayment = upcoming.find((d) => d.kind === "payment" && d.status === "open");
  const paymentTerm = c.payment_terms.find((p) => p.id === nextPayment?.payment_term_id);
  const term = termSentence(c);
  const notices = c.date_rules.filter((r) => r.review_status !== "rejected");
  const pending = c.pending_review ?? 0;

  return (
    <Card title="At a glance">
      {pending > 0 && (
        <div className="border-warning/30 bg-warning/5 mb-2 flex flex-wrap items-center justify-between gap-2 rounded-md border px-3 py-2 text-sm">
          <span>
            {pending} item{pending === 1 ? "" : "s"} found by AI {pending === 1 ? "needs" : "need"}{" "}
            a quick check before reminders are sent.
          </span>
          <button className="text-primary font-medium hover:underline" onClick={onReview}>
            Check now
          </button>
        </div>
      )}
      <dl className="divide-border divide-y">
        <Row label="Next step">
          {next ? (
            <div className="bg-primary/[0.04] ring-primary/10 flex gap-4 rounded-xl p-4 ring-1">
              <DateTile date={next.due_date} className="size-14" />
              <div className="min-w-0 flex-1 space-y-2">
                <div>
                  <p className="font-medium">
                    {deadlineSentence({ ...next, counterparty_name: c.counterparty_name })}
                  </p>
                  <DueText date={next.due_date} />
                </div>
                {canEdit && (
                  <QuickActions
                    orgId={orgId}
                    deadline={{ ...next, contract_title: c.title }}
                    onDone={toast.show}
                  />
                )}
              </div>
            </div>
          ) : lastDecided?.decision ? (
            <p>
              Decided: <Badge tone="primary">{DECISION_LABELS[lastDecided.decision]}</Badge>{" "}
              <span className="text-muted">
                ({lastDecided.label}, {formatIsoDate(lastDecided.due_date)})
              </span>
            </p>
          ) : (
            <p className="text-muted">Nothing coming up.</p>
          )}
        </Row>
        <Row label="Term">{term ?? <span className="text-muted">Not entered yet.</span>}</Row>
        <Row label="Notice">
          {notices.length ? (
            <ul className="space-y-0.5">
              {notices.map((r) => (
                <li key={r.id}>
                  <span className="font-medium">{r.label}:</span> {describeRule(r)}
                </li>
              ))}
            </ul>
          ) : (
            <span className="text-muted">No notice period entered.</span>
          )}
          {c.notice_details && <p className="text-muted mt-1">How: {c.notice_details}</p>}
        </Row>
        {nextPayment && (
          <Row label="Next payment">
            {paymentTerm
              ? [
                  paymentTerm.description,
                  formatMoney(paymentTerm.amount, paymentTerm.currency ?? c.currency),
                  FREQUENCY_LABELS[paymentTerm.frequency].toLowerCase(),
                ]
                  .filter(Boolean)
                  .join(" · ")
              : nextPayment.label}
            <span className="block">
              <DueText date={nextPayment.due_date} />
            </span>
          </Row>
        )}
        <Row label="Also remind">
          <AlsoRemind orgId={orgId} contract={c} canEdit={canEdit} />
        </Row>
        {c.summary && <Row label="Summary">{c.summary}</Row>}
      </dl>
      {toast.node}
    </Card>
  );
}
