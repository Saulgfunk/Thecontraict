"use client";

import { Check, FileText, Pencil, Plus, X } from "lucide-react";
import { useState } from "react";

import {
  Confidence,
  Countdown,
  ReviewBadge,
  SourceRefs,
  describeRule,
  formatIsoDate,
} from "@/components/app/contract-bits";
import { NoticeDraftDialog } from "@/components/app/notice-draft-dialog";
import { Badge, Button, Card, ErrorText, Field, Input, Select } from "@/components/ui";
import {
  useAiEnabled,
  useCreateDateRule,
  useCreatePaymentTerm,
  useUpdateDateRule,
  useUpdateDeadline,
  useUpdatePaymentTerm,
  type Schemas,
} from "@/lib/api";
import {
  ANCHOR_LABELS,
  DECISION_LABELS,
  DEADLINE_KIND_LABELS,
  FREQUENCY_LABELS,
  PAYMENT_DIRECTION_LABELS,
  RULE_TYPE_LABELS,
} from "@/lib/labels";
import { cn, errorMessage } from "@/lib/utils";

type Rule = Schemas["DateRuleOut"];
type RuleUpdate = Schemas["DateRuleUpdate"];

// ---------------------------------------------------------------------------
// Deadlines
// ---------------------------------------------------------------------------

const DECIDABLE: Schemas["DeadlineKind"][] = [
  "notice",
  "option",
  "term_end",
  "price_review",
  "other",
];

function DeadlineItem({
  orgId,
  contract,
  deadline: d,
  canEdit,
  onDraft,
}: {
  orgId: string;
  contract: Schemas["ContractDetail"];
  deadline: Schemas["DeadlineOut"];
  canEdit: boolean;
  onDraft: (d: Schemas["DeadlineOut"]) => void;
}) {
  const update = useUpdateDeadline(orgId);
  const [deciding, setDeciding] = useState(false);
  const [decision, setDecision] = useState<Schemas["DeadlineDecision"]>(
    d.decision ?? (d.kind === "option" ? "exercise_option" : "renew"),
  );
  const [note, setNote] = useState(d.decision_note ?? "");
  const closed = d.status !== "open";
  const aiEnabled = useAiEnabled();
  const canDraft =
    !!aiEnabled &&
    canEdit &&
    (d.kind === "notice" || d.kind === "option") &&
    !!contract.documents.length;

  return (
    <li className="py-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className={cn("min-w-0", closed && !d.decision && "text-muted line-through")}>
          <p className="font-medium">{d.label}</p>
          <p className="text-muted text-sm">
            {formatIsoDate(d.due_date)} · {DEADLINE_KIND_LABELS[d.kind]}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {!d.confirmed && <Badge tone="warning">Unconfirmed</Badge>}
          {d.decision ? (
            <Badge tone="primary">Decided: {DECISION_LABELS[d.decision]}</Badge>
          ) : closed ? (
            <Badge>{d.status === "done" ? "Done" : "Dismissed"}</Badge>
          ) : (
            <Countdown date={d.due_date} />
          )}
          {canDraft && (
            <Button variant="secondary" className="h-8 px-2 text-xs" onClick={() => onDraft(d)}>
              <FileText className="size-3.5" /> Draft notice
            </Button>
          )}
          {canEdit && DECIDABLE.includes(d.kind) && !deciding && (
            <Button variant="ghost" className="h-8 px-2 text-xs" onClick={() => setDeciding(true)}>
              {d.decision ? "Change decision" : "Decide"}
            </Button>
          )}
          {canEdit && !d.decision && (
            <Button
              variant="ghost"
              className="h-8 px-2 text-xs"
              onClick={() => update.mutate({ id: d.id, status: closed ? "open" : "done" })}
            >
              {closed ? "Reopen" : "Mark done"}
            </Button>
          )}
        </div>
      </div>
      {d.decision && d.decision_note && !deciding && (
        <p className="text-muted mt-1 text-sm">
          “{d.decision_note}”
          {d.decided_at ? ` · ${new Date(d.decided_at).toLocaleDateString()}` : ""}
        </p>
      )}
      {deciding && (
        <form
          className="border-border mt-2 flex flex-wrap items-end gap-2 rounded-md border p-3"
          onSubmit={(e) => {
            e.preventDefault();
            update.mutate(
              { id: d.id, decision, decision_note: note || null },
              { onSuccess: () => setDeciding(false) },
            );
          }}
        >
          <Field label="Decision">
            <Select
              value={decision}
              onChange={(e) => setDecision(e.target.value as Schemas["DeadlineDecision"])}
            >
              {Object.entries(DECISION_LABELS).map(([v, l]) => (
                <option key={v} value={v}>
                  {l}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Note (optional)" className="min-w-56 flex-1">
            <Input
              value={note}
              placeholder="Why, and any next steps"
              onChange={(e) => setNote(e.target.value)}
            />
          </Field>
          <Button type="submit" disabled={update.isPending}>
            Save
          </Button>
          {d.decision && (
            <Button
              type="button"
              variant="ghost"
              onClick={() =>
                update.mutate(
                  { id: d.id, decision: null, status: "open" },
                  { onSuccess: () => setDeciding(false) },
                )
              }
            >
              Clear decision
            </Button>
          )}
          <Button type="button" variant="ghost" onClick={() => setDeciding(false)}>
            Cancel
          </Button>
        </form>
      )}
      <details className="text-muted mt-1 text-xs">
        <summary className="cursor-pointer select-none">How this was calculated</summary>
        <ol className="bg-background mt-1 space-y-0.5 rounded p-2 font-mono">
          {d.derivation.map((s, i) => (
            <li key={i}>{s}</li>
          ))}
        </ol>
      </details>
      <ErrorText>{errorMessage(update.error)}</ErrorText>
    </li>
  );
}

export function DeadlinesCard({
  orgId,
  contract,
  canEdit,
}: {
  orgId: string;
  contract: Schemas["ContractDetail"];
  canEdit: boolean;
}) {
  const [showPast, setShowPast] = useState(false);
  const [drafting, setDrafting] = useState<Schemas["DeadlineOut"] | null | undefined>(undefined);
  const aiEnabled = useAiEnabled();
  const today = new Date().toISOString().slice(0, 10);
  const all = contract.deadlines;
  // By default show what needs attention: open and upcoming deadlines (and upcoming ones
  // with a recorded decision), but only the next occurrence of each recurring payment.
  const seenPayments = new Set<string>();
  const visible = showPast
    ? all
    : all.filter((d) => {
        if (d.status !== "open") return !!d.decision && d.due_date >= today;
        if (d.kind !== "payment" || !d.payment_term_id) return d.due_date >= today;
        if (d.due_date < today) return true;
        if (seenPayments.has(d.payment_term_id)) return false;
        seenPayments.add(d.payment_term_id);
        return true;
      });
  const hidden = all.length - visible.length;

  return (
    <Card
      title="Deadlines"
      description="Calculated from the terms and rules below. Record what you decide for each."
      actions={
        aiEnabled && canEdit && contract.documents.length ? (
          <Button variant="secondary" onClick={() => setDrafting(null)}>
            <FileText className="size-4" /> Draft a notice
          </Button>
        ) : null
      }
    >
      {visible.length === 0 ? (
        <p className="text-muted text-sm">
          No deadlines yet. Confirm the key terms or add a date rule.
        </p>
      ) : (
        <ul className="divide-border divide-y">
          {visible.map((d) => (
            <DeadlineItem
              key={d.id}
              orgId={orgId}
              contract={contract}
              deadline={d}
              canEdit={canEdit}
              onDraft={setDrafting}
            />
          ))}
        </ul>
      )}
      {hidden > 0 && (
        <button
          className="text-primary mt-2 text-xs hover:underline"
          onClick={() => setShowPast(true)}
        >
          Show all ({hidden} more: later payments, past or closed)
        </button>
      )}
      {drafting !== undefined && (
        <NoticeDraftDialog
          orgId={orgId}
          contract={contract}
          deadline={drafting ?? undefined}
          onClose={() => setDrafting(undefined)}
        />
      )}
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Date rules
// ---------------------------------------------------------------------------

function RuleForm({
  initial,
  onSubmit,
  onCancel,
  pending,
}: {
  initial: Partial<Rule>;
  onSubmit: (body: Schemas["DateRuleIn"]) => void;
  onCancel: () => void;
  pending: boolean;
}) {
  const [rule, setRule] = useState({
    rule_type: initial.rule_type ?? "other",
    label: initial.label ?? "",
    anchor: initial.anchor ?? "term_end",
    fixed_date: initial.fixed_date ?? "",
    offset_amount: initial.offset_amount?.toString() ?? "",
    offset_unit: initial.offset_unit ?? "days",
    offset_basis: initial.offset_basis ?? "calendar",
    direction: initial.direction ?? "before",
    delivery_amount: initial.delivery_amount?.toString() ?? "",
  });
  const set = (key: keyof typeof rule, value: string) => setRule((r) => ({ ...r, [key]: value }));

  return (
    <form
      className="border-border grid gap-3 rounded-md border p-3 sm:grid-cols-2"
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit({
          rule_type: rule.rule_type as Schemas["DateRuleType"],
          label: rule.label || RULE_TYPE_LABELS[rule.rule_type as Schemas["DateRuleType"]],
          anchor: rule.anchor as Schemas["DateAnchor"],
          fixed_date: rule.anchor === "fixed_date" ? rule.fixed_date || null : null,
          offset_amount: rule.offset_amount === "" ? null : Number(rule.offset_amount),
          offset_unit:
            rule.offset_amount === "" ? null : (rule.offset_unit as Schemas["PeriodUnit"]),
          offset_basis:
            rule.offset_unit === "days" ? (rule.offset_basis as Schemas["DayBasis"]) : "calendar",
          direction: rule.direction as Schemas["OffsetDirection"],
          delivery_amount: rule.delivery_amount === "" ? null : Number(rule.delivery_amount),
        });
      }}
    >
      <Field label="Type">
        <Select value={rule.rule_type} onChange={(e) => set("rule_type", e.target.value)}>
          {Object.entries(RULE_TYPE_LABELS).map(([v, l]) => (
            <option key={v} value={v}>
              {l}
            </option>
          ))}
        </Select>
      </Field>
      <Field label="Label">
        <Input value={rule.label} onChange={(e) => set("label", e.target.value)} />
      </Field>
      <Field label="Period">
        <div className="flex gap-2">
          <Input
            type="number"
            min={0}
            className="w-20 shrink-0"
            value={rule.offset_amount}
            onChange={(e) => set("offset_amount", e.target.value)}
          />
          <Select
            value={rule.offset_unit === "days" ? `days_${rule.offset_basis}` : rule.offset_unit}
            onChange={(e) => {
              const [unit, basis] = e.target.value.split("_");
              setRule((r) => ({
                ...r,
                offset_unit: unit as never,
                offset_basis: (basis ?? "calendar") as never,
              }));
            }}
          >
            <option value="days_calendar">calendar days</option>
            <option value="days_business">business days</option>
            <option value="weeks">weeks</option>
            <option value="months">months</option>
            <option value="years">years</option>
          </Select>
        </div>
      </Field>
      <Field label="Relative to">
        <div className="flex gap-2">
          <Select
            className="w-28 shrink-0"
            value={rule.direction}
            onChange={(e) => set("direction", e.target.value)}
          >
            <option value="before">before</option>
            <option value="after">after</option>
          </Select>
          <Select value={rule.anchor} onChange={(e) => set("anchor", e.target.value)}>
            {Object.entries(ANCHOR_LABELS).map(([v, l]) => (
              <option key={v} value={v}>
                {l}
              </option>
            ))}
          </Select>
        </div>
      </Field>
      {rule.anchor === "fixed_date" && (
        <Field label="Date">
          <Input
            type="date"
            required
            value={rule.fixed_date}
            onChange={(e) => set("fixed_date", e.target.value)}
          />
        </Field>
      )}
      <Field label="Deemed receipt delay" hint="Business days, if notices take effect later">
        <Input
          type="number"
          min={0}
          value={rule.delivery_amount}
          onChange={(e) => set("delivery_amount", e.target.value)}
        />
      </Field>
      <div className="flex gap-2 sm:col-span-2">
        <Button type="submit" disabled={pending}>
          Save
        </Button>
        <Button type="button" variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

function RuleItem({
  orgId,
  rule,
  canEdit,
  onSelectRefs,
}: {
  orgId: string;
  rule: Rule;
  canEdit: boolean;
  onSelectRefs: (refs: string[]) => void;
}) {
  const update = useUpdateDateRule(orgId);
  const [editing, setEditing] = useState(false);
  const rejected = rule.review_status === "rejected";
  const decide = (body: RuleUpdate) => update.mutate({ id: rule.id, body });

  if (editing) {
    return (
      <li className="py-3">
        <RuleForm
          initial={rule}
          pending={update.isPending}
          onCancel={() => setEditing(false)}
          onSubmit={(body) => {
            update.mutate({ id: rule.id, body }, { onSuccess: () => setEditing(false) });
          }}
        />
      </li>
    );
  }
  return (
    <li className={cn("py-3", rejected && "opacity-60")}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className={cn("font-medium", rejected && "line-through")}>{rule.label}</p>
          <p className="text-sm">{describeRule(rule)}</p>
          {rule.compute_error && !rejected && (
            <p className="text-warning text-sm">Can&apos;t calculate yet: {rule.compute_error}</p>
          )}
          <SourceRefs refs={rule.source_clause_refs} quote={rule.quote} onSelect={onSelectRefs} />
        </div>
        <div className="flex items-center gap-2">
          {rule.review_status === "ai_suggested" && <Confidence value={rule.confidence} />}
          <ReviewBadge status={rule.review_status} />
        </div>
      </div>
      {canEdit && (
        <div className="mt-2 flex flex-wrap gap-2">
          {rule.review_status !== "confirmed" && !rejected && (
            <Button
              variant="secondary"
              className="h-8 px-3"
              onClick={() => decide({ review_status: "confirmed" })}
            >
              <Check className="size-3.5" /> Confirm
            </Button>
          )}
          <Button variant="secondary" className="h-8 px-3" onClick={() => setEditing(true)}>
            <Pencil className="size-3.5" /> Edit
          </Button>
          {rejected ? (
            <Button
              variant="ghost"
              className="h-8 px-3"
              onClick={() => decide({ review_status: "ai_suggested" })}
            >
              Restore
            </Button>
          ) : (
            <Button
              variant="danger"
              className="h-8 px-3"
              onClick={() => decide({ review_status: "rejected" })}
            >
              <X className="size-3.5" /> Reject
            </Button>
          )}
        </div>
      )}
      <ErrorText>{errorMessage(update.error)}</ErrorText>
    </li>
  );
}

export function DateRulesCard({
  orgId,
  contract,
  canEdit,
  onSelectRefs,
}: {
  orgId: string;
  contract: Schemas["ContractDetail"];
  canEdit: boolean;
  onSelectRefs: (refs: string[]) => void;
}) {
  const create = useCreateDateRule(orgId, contract.id);
  const [adding, setAdding] = useState(false);
  return (
    <Card
      title="Notice periods and key dates"
      description="Rules found in the contract. Confirm, correct or reject each one."
      actions={
        canEdit && !adding ? (
          <Button variant="secondary" onClick={() => setAdding(true)}>
            <Plus className="size-4" /> Add
          </Button>
        ) : null
      }
    >
      {adding && (
        <div className="mb-4">
          <RuleForm
            initial={{ rule_type: "non_renewal_notice", label: "Notice of non-renewal" }}
            pending={create.isPending}
            onCancel={() => setAdding(false)}
            onSubmit={(body) => create.mutate(body, { onSuccess: () => setAdding(false) })}
          />
          <ErrorText>{errorMessage(create.error)}</ErrorText>
        </div>
      )}
      {contract.date_rules.length === 0 ? (
        <p className="text-muted text-sm">None yet.</p>
      ) : (
        <ul className="divide-border divide-y">
          {contract.date_rules.map((r) => (
            <RuleItem
              key={r.id}
              orgId={orgId}
              rule={r}
              canEdit={canEdit}
              onSelectRefs={onSelectRefs}
            />
          ))}
        </ul>
      )}
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Payment terms
// ---------------------------------------------------------------------------

function formatMoney(amount: string | number | null | undefined, currency: string | null) {
  if (amount == null) return null;
  const value = Number(amount);
  try {
    return new Intl.NumberFormat(undefined, {
      style: currency ? "currency" : "decimal",
      currency: currency ?? undefined,
    }).format(value);
  } catch {
    return `${value} ${currency ?? ""}`.trim();
  }
}

function PaymentForm({
  orgId,
  contract,
  onDone,
}: {
  orgId: string;
  contract: Schemas["ContractDetail"];
  onDone: () => void;
}) {
  const create = useCreatePaymentTerm(orgId, contract.id);
  const [p, setP] = useState({
    description: "",
    amount: "",
    frequency: "monthly" as Schemas["PaymentFrequency"],
    first_due_date: "",
    payment_days: "",
    direction: "payable" as Schemas["PaymentDirection"],
  });
  const set = (key: keyof typeof p, value: string) => setP((s) => ({ ...s, [key]: value }));
  return (
    <form
      className="border-border mb-4 grid gap-3 rounded-md border p-3 sm:grid-cols-3"
      onSubmit={(e) => {
        e.preventDefault();
        create.mutate(
          {
            description: p.description.trim(),
            amount: p.amount || null,
            currency: contract.currency ?? null,
            frequency: p.frequency,
            first_due_date: p.first_due_date || null,
            payment_days: p.payment_days ? Number(p.payment_days) : null,
            direction: p.direction,
          },
          { onSuccess: onDone },
        );
      }}
    >
      <Field label="Description" className="sm:col-span-2">
        <Input
          required
          autoFocus
          value={p.description}
          placeholder="e.g. Monthly fee"
          onChange={(e) => set("description", e.target.value)}
        />
      </Field>
      <Field label={`Amount${contract.currency ? ` (${contract.currency})` : ""}`}>
        <Input
          type="number"
          step="0.01"
          value={p.amount}
          onChange={(e) => set("amount", e.target.value)}
        />
      </Field>
      <Field label="How often">
        <Select value={p.frequency} onChange={(e) => set("frequency", e.target.value)}>
          {Object.entries(FREQUENCY_LABELS).map(([v, l]) => (
            <option key={v} value={v}>
              {l}
            </option>
          ))}
        </Select>
      </Field>
      <Field label="First due">
        <Input
          type="date"
          value={p.first_due_date}
          onChange={(e) => set("first_due_date", e.target.value)}
        />
      </Field>
      <Field label="Who pays">
        <Select value={p.direction} onChange={(e) => set("direction", e.target.value)}>
          <option value="payable">We pay</option>
          <option value="receivable">We receive</option>
          <option value="unknown">Not sure</option>
        </Select>
      </Field>
      <Field label="Payable within (days)">
        <Input
          type="number"
          min={0}
          value={p.payment_days}
          onChange={(e) => set("payment_days", e.target.value)}
        />
      </Field>
      <div className="flex items-end gap-2 sm:col-span-2">
        <Button type="submit" disabled={create.isPending}>
          Save
        </Button>
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancel
        </Button>
        <ErrorText>{errorMessage(create.error)}</ErrorText>
      </div>
    </form>
  );
}

export function PaymentTermsCard({
  orgId,
  contract,
  canEdit,
  onSelectRefs,
}: {
  orgId: string;
  contract: Schemas["ContractDetail"];
  canEdit: boolean;
  onSelectRefs: (refs: string[]) => void;
}) {
  const update = useUpdatePaymentTerm(orgId);
  const [adding, setAdding] = useState(false);
  return (
    <Card
      title="Payments and invoicing"
      description="Used for invoice and payment reminders."
      actions={
        canEdit && !adding ? (
          <Button variant="secondary" onClick={() => setAdding(true)}>
            <Plus className="size-4" /> Add
          </Button>
        ) : null
      }
    >
      {adding && <PaymentForm orgId={orgId} contract={contract} onDone={() => setAdding(false)} />}
      {contract.payment_terms.length === 0 ? (
        !adding && <p className="text-muted text-sm">None yet.</p>
      ) : (
        <ul className="divide-border divide-y">
          {contract.payment_terms.map((p) => {
            const rejected = p.review_status === "rejected";
            return (
              <li key={p.id} className={cn("py-3", rejected && "opacity-60")}>
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className={cn("font-medium", rejected && "line-through")}>{p.description}</p>
                    <p className="text-sm">
                      {[
                        formatMoney(p.amount, p.currency),
                        FREQUENCY_LABELS[p.frequency],
                        p.first_due_date ? `from ${formatIsoDate(p.first_due_date)}` : null,
                        p.payment_days ? `payable within ${p.payment_days} days` : null,
                        PAYMENT_DIRECTION_LABELS[p.direction],
                      ]
                        .filter(Boolean)
                        .join(" · ")}
                    </p>
                    {p.escalation && (
                      <p className="text-muted text-sm">Escalation: {p.escalation}</p>
                    )}
                    {!p.first_due_date && !rejected && (
                      <p className="text-warning text-sm">
                        No first due date, so no reminders yet.
                      </p>
                    )}
                    <SourceRefs
                      refs={p.source_clause_refs}
                      quote={p.quote}
                      onSelect={onSelectRefs}
                    />
                  </div>
                  <div className="flex items-center gap-2">
                    {p.review_status === "ai_suggested" && <Confidence value={p.confidence} />}
                    <ReviewBadge status={p.review_status} />
                  </div>
                </div>
                {canEdit && (
                  <div className="mt-2 flex flex-wrap items-end gap-2">
                    {!p.first_due_date && !rejected && (
                      <Input
                        type="date"
                        aria-label="First due date"
                        className="h-8 w-40"
                        onChange={(e) =>
                          e.target.value &&
                          update.mutate({ id: p.id, body: { first_due_date: e.target.value } })
                        }
                      />
                    )}
                    {p.review_status !== "confirmed" && !rejected && (
                      <Button
                        variant="secondary"
                        className="h-8 px-3"
                        onClick={() =>
                          update.mutate({ id: p.id, body: { review_status: "confirmed" } })
                        }
                      >
                        <Check className="size-3.5" /> Confirm
                      </Button>
                    )}
                    {rejected ? (
                      <Button
                        variant="ghost"
                        className="h-8 px-3"
                        onClick={() =>
                          update.mutate({ id: p.id, body: { review_status: "ai_suggested" } })
                        }
                      >
                        Restore
                      </Button>
                    ) : (
                      <Button
                        variant="danger"
                        className="h-8 px-3"
                        onClick={() =>
                          update.mutate({ id: p.id, body: { review_status: "rejected" } })
                        }
                      >
                        <X className="size-3.5" /> Reject
                      </Button>
                    )}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
      <ErrorText>{errorMessage(update.error)}</ErrorText>
    </Card>
  );
}
