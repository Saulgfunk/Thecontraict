"use client";

import { ExternalLink, FilePlus2, Trash2, Upload, X } from "lucide-react";
import { useRef, useState } from "react";

import { formatIsoDate, formatPeriod } from "@/components/app/contract-bits";
import { Badge, Button, Card, ErrorText, Field, Input, Select } from "@/components/ui";
import {
  useAttachAmendmentDocument,
  useCreateAmendment,
  useDeleteAmendment,
  useOpenDocument,
  type Schemas,
} from "@/lib/api";
import { FREQUENCY_LABELS } from "@/lib/labels";
import { errorMessage } from "@/lib/utils";

type Contract = Schemas["ContractDetail"];
type Change = Schemas["AmendmentChangeOut"];
type Unit = Schemas["PeriodUnit"];
const UNITS: Unit[] = ["days", "weeks", "months", "years"];

const FIELD_LABELS: Record<string, string> = {
  title: "Title",
  counterparty_name: "Other party",
  contract_type: "Type",
  end_date: "End date",
  initial_term_amount: "Initial term",
  initial_term_unit: "Initial term",
  auto_renews: "Renews automatically",
  renewal_term_amount: "Renewal term",
  renewal_term_unit: "Renewal term",
  governing_law: "Governing law",
  holiday_country: "Holiday calendar",
  currency: "Currency",
  contract_value: "Contract value",
  notice_details: "How to give notice",
  label: "Name",
  offset_amount: "Period",
  offset_unit: "Period unit",
  offset_basis: "Day basis",
  delivery_amount: "Deemed receipt (business days)",
  fixed_date: "Date",
  amount: "Amount",
  frequency: "Frequency",
  first_due_date: "First due",
  payment_days: "Payable within (days)",
  description: "Description",
};

function show(value: unknown, field: string): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "yes" : "no";
  if (typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value)) return formatIsoDate(value);
  if (field === "amount" || field === "contract_value") {
    const n = Number(value);
    if (!Number.isNaN(n)) return n.toLocaleString(undefined, { maximumFractionDigits: 2 });
  }
  if (field === "frequency")
    return FREQUENCY_LABELS[value as Schemas["PaymentFrequency"]] ?? String(value);
  return String(value);
}

/** Merge "_amount"/"_unit" pairs into one readable line. */
function describeChanges(changes: Change[], contract: Contract): string[] {
  const lines: string[] = [];
  const done = new Set<number>();
  changes.forEach((ch, i) => {
    if (done.has(i)) return;
    const target = ch.target_type === "contract" ? "" : `${ch.label}: `;
    if (ch.field === "_created") {
      lines.push(`Added ${ch.target_type === "date_rule" ? "date rule" : "payment"}: ${ch.label}`);
      return;
    }
    const m = ch.field.match(/^(initial_term|renewal_term|offset)_(amount|unit)$/);
    if (m) {
      const prefix = m[1];
      const otherField = `${prefix}_${m[2] === "amount" ? "unit" : "amount"}`;
      const j = changes.findIndex(
        (c, k) => k !== i && c.target_id === ch.target_id && c.field === otherField,
      );
      if (j >= 0) done.add(j);
      const other = j >= 0 ? changes[j] : null;
      const current =
        ch.target_type === "contract"
          ? (contract as unknown as Record<string, unknown>)[otherField]
          : contract.date_rules.find((r) => r.id === ch.target_id)?.[
              otherField as keyof Schemas["DateRuleOut"]
            ];
      const amount = (which: "old_value" | "new_value") =>
        (m[2] === "amount" ? ch[which] : (other?.[which] ?? current)) as number | null;
      const unit = (which: "old_value" | "new_value") =>
        (m[2] === "unit" ? ch[which] : (other?.[which] ?? current)) as string | null;
      const name = prefix === "offset" ? "Period" : FIELD_LABELS[ch.field];
      lines.push(
        `${target}${name}: ${formatPeriod(amount("old_value"), unit("old_value"))} → ${formatPeriod(amount("new_value"), unit("new_value"))}`,
      );
      return;
    }
    const name = FIELD_LABELS[ch.field] ?? ch.field.replace(/_/g, " ");
    lines.push(
      `${target}${name}: ${show(ch.old_value, ch.field)} → ${show(ch.new_value, ch.field)}`,
    );
  });
  return lines;
}

// ---------------------------------------------------------------------------
// Form
// ---------------------------------------------------------------------------

const asStr = (v: unknown) => (v === null || v === undefined ? "" : String(v));

function AmendmentDialog({
  orgId,
  contract,
  onClose,
}: {
  orgId: string;
  contract: Contract;
  onClose: () => void;
}) {
  const create = useCreateAmendment(orgId, contract.id);
  const attach = useAttachAmendmentDocument(orgId);
  const initial = {
    end_date: asStr(contract.end_date),
    initial_term_amount: asStr(contract.initial_term_amount),
    initial_term_unit: asStr(contract.initial_term_unit) || "months",
    auto_renews: contract.auto_renews == null ? "" : contract.auto_renews ? "yes" : "no",
    renewal_term_amount: asStr(contract.renewal_term_amount),
    renewal_term_unit: asStr(contract.renewal_term_unit) || "months",
    contract_value: contract.contract_value ? String(Number(contract.contract_value)) : "",
    counterparty_name: asStr(contract.counterparty_name),
    governing_law: asStr(contract.governing_law),
    notice_details: asStr(contract.notice_details),
  };
  const [meta, setMeta] = useState({
    title: `Amendment No. ${(contract.amendments ?? []).length + 1}`,
    effective_date: "",
    signed_date: "",
    description: "",
  });
  const [terms, setTerms] = useState(initial);
  const [rules, setRules] = useState(
    Object.fromEntries(
      contract.date_rules
        .filter((r) => r.review_status !== "rejected")
        .map((r) => [r.id, { amount: asStr(r.offset_amount), delivery: asStr(r.delivery_amount) }]),
    ),
  );
  const [payments, setPayments] = useState(
    Object.fromEntries(
      contract.payment_terms
        .filter((p) => p.review_status !== "rejected")
        .map((p) => [
          p.id,
          {
            amount: p.amount ? String(Number(p.amount)) : "",
            frequency: p.frequency as string,
            first_due_date: asStr(p.first_due_date),
          },
        ]),
    ),
  );
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Only send what actually changed.
  const contractChanges: Record<string, unknown> = {};
  const t = terms;
  if (t.end_date !== initial.end_date) contractChanges.end_date = t.end_date || null;
  if (
    t.initial_term_amount !== initial.initial_term_amount ||
    t.initial_term_unit !== initial.initial_term_unit
  ) {
    contractChanges.initial_term_amount = t.initial_term_amount
      ? Number(t.initial_term_amount)
      : null;
    contractChanges.initial_term_unit = t.initial_term_amount ? t.initial_term_unit : null;
  }
  if (t.auto_renews !== initial.auto_renews)
    contractChanges.auto_renews = t.auto_renews === "" ? null : t.auto_renews === "yes";
  if (
    t.renewal_term_amount !== initial.renewal_term_amount ||
    t.renewal_term_unit !== initial.renewal_term_unit
  ) {
    contractChanges.renewal_term_amount = t.renewal_term_amount
      ? Number(t.renewal_term_amount)
      : null;
    contractChanges.renewal_term_unit = t.renewal_term_amount ? t.renewal_term_unit : null;
  }
  for (const key of [
    "contract_value",
    "counterparty_name",
    "governing_law",
    "notice_details",
  ] as const) {
    if (t[key] !== initial[key]) contractChanges[key] = t[key].trim() || null;
  }
  const ruleChanges = contract.date_rules
    .filter((r) => rules[r.id])
    .flatMap((r) => {
      const v = rules[r.id];
      const change: Schemas["AmendmentRuleChange"] = { date_rule_id: r.id };
      if (v.amount !== asStr(r.offset_amount))
        change.offset_amount = v.amount ? Number(v.amount) : null;
      if (v.delivery !== asStr(r.delivery_amount))
        change.delivery_amount = v.delivery ? Number(v.delivery) : null;
      return Object.keys(change).length > 1 ? [change] : [];
    });
  const paymentChanges = contract.payment_terms
    .filter((p) => payments[p.id])
    .flatMap((p) => {
      const v = payments[p.id];
      const change: Schemas["AmendmentPaymentChange"] = { payment_term_id: p.id };
      if (v.amount !== (p.amount ? String(Number(p.amount)) : "")) change.amount = v.amount || null;
      if (v.frequency !== p.frequency)
        change.frequency = v.frequency as Schemas["PaymentFrequency"];
      if (v.first_due_date !== asStr(p.first_due_date))
        change.first_due_date = v.first_due_date || null;
      return Object.keys(change).length > 1 ? [change] : [];
    });
  // Count what the user will see: a term's number and unit are one change.
  const contractCount = Object.keys(contractChanges).filter((k) => !k.endsWith("_unit")).length;
  const changeCount = contractCount + ruleChanges.length + paymentChanges.length;
  const busy = create.isPending || attach.isPending;

  const submit = async () => {
    setError(null);
    try {
      const amendment = (await create.mutateAsync({
        title: meta.title.trim(),
        effective_date: meta.effective_date || null,
        signed_date: meta.signed_date || null,
        description: meta.description.trim() || null,
        contract: contractChanges as Schemas["AmendmentContractChanges"],
        date_rules: ruleChanges,
        payment_terms: paymentChanges,
      })) as Schemas["AmendmentOut"];
      if (file) await attach.mutateAsync({ amendmentId: amendment.id, file });
      onClose();
    } catch (e) {
      setError(errorMessage(e));
    }
  };

  const setT = (key: keyof typeof terms, value: string) =>
    setTerms((s) => ({ ...s, [key]: value }));
  const changed = (key: keyof typeof terms) => terms[key] !== initial[key];
  const mark = (on: boolean) => (on ? "ring-2 ring-primary/40" : "");

  return (
    <div
      className="fixed inset-0 z-30 flex items-start justify-center overflow-y-auto bg-black/40 p-4 md:p-10"
      role="dialog"
      aria-modal="true"
      aria-label="Record an amendment"
    >
      <form
        className="border-border bg-surface w-full max-w-3xl rounded-lg border shadow-xl"
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
      >
        <header className="border-border flex items-center justify-between border-b px-5 py-4">
          <div>
            <h2 className="font-semibold">Record an amendment</h2>
            <p className="text-muted text-sm">
              Change the values the amendment changes. The contract will show the amended terms and
              deadlines are recalculated; the previous values are kept in the history.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="text-muted hover:text-foreground rounded p-1"
          >
            <X className="size-5" />
          </button>
        </header>

        <div className="space-y-6 p-5">
          <section className="grid gap-3 sm:grid-cols-3">
            <Field label="Title" className="sm:col-span-3">
              <Input
                required
                value={meta.title}
                onChange={(e) => setMeta({ ...meta, title: e.target.value })}
              />
            </Field>
            <Field label="Effective from">
              <Input
                type="date"
                value={meta.effective_date}
                onChange={(e) => setMeta({ ...meta, effective_date: e.target.value })}
              />
            </Field>
            <Field label="Signed on">
              <Input
                type="date"
                value={meta.signed_date}
                onChange={(e) => setMeta({ ...meta, signed_date: e.target.value })}
              />
            </Field>
            <Field label="Amendment document (optional)">
              <Input
                type="file"
                accept=".pdf,.docx"
                className="h-auto py-1.5"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              />
            </Field>
            <Field label="What it does (optional)" className="sm:col-span-3">
              <Input
                value={meta.description}
                placeholder="e.g. Extends the term by 12 months and increases the fee by 10%"
                onChange={(e) => setMeta({ ...meta, description: e.target.value })}
              />
            </Field>
          </section>

          <section>
            <h3 className="mb-2 text-sm font-semibold">Term and renewal</h3>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Initial term">
                <div className="flex gap-2">
                  <Input
                    type="number"
                    min={1}
                    className={`w-20 shrink-0 ${mark(changed("initial_term_amount"))}`}
                    value={terms.initial_term_amount}
                    onChange={(e) => setT("initial_term_amount", e.target.value)}
                  />
                  <Select
                    className={mark(changed("initial_term_unit"))}
                    value={terms.initial_term_unit}
                    onChange={(e) => setT("initial_term_unit", e.target.value)}
                  >
                    {UNITS.map((u) => (
                      <option key={u}>{u}</option>
                    ))}
                  </Select>
                </div>
              </Field>
              <Field label="Fixed end date">
                <Input
                  type="date"
                  className={mark(changed("end_date"))}
                  value={terms.end_date}
                  onChange={(e) => setT("end_date", e.target.value)}
                />
              </Field>
              <Field label="Renews automatically?">
                <Select
                  className={mark(changed("auto_renews"))}
                  value={terms.auto_renews}
                  onChange={(e) => setT("auto_renews", e.target.value)}
                >
                  <option value="yes">Yes</option>
                  <option value="no">No</option>
                  <option value="">Unknown</option>
                </Select>
              </Field>
              <Field label="Each renewal lasts">
                <div className="flex gap-2">
                  <Input
                    type="number"
                    min={1}
                    className={`w-20 shrink-0 ${mark(changed("renewal_term_amount"))}`}
                    value={terms.renewal_term_amount}
                    onChange={(e) => setT("renewal_term_amount", e.target.value)}
                  />
                  <Select
                    className={mark(changed("renewal_term_unit"))}
                    value={terms.renewal_term_unit}
                    onChange={(e) => setT("renewal_term_unit", e.target.value)}
                  >
                    {UNITS.map((u) => (
                      <option key={u}>{u}</option>
                    ))}
                  </Select>
                </div>
              </Field>
            </div>
          </section>

          {contract.date_rules.some((r) => rules[r.id]) && (
            <section>
              <h3 className="mb-2 text-sm font-semibold">Notice periods and key dates</h3>
              <div className="space-y-2">
                {contract.date_rules
                  .filter((r) => rules[r.id])
                  .map((r) => (
                    <div key={r.id} className="grid items-end gap-3 sm:grid-cols-3">
                      <p className="text-sm sm:pb-2">{r.label}</p>
                      <Field label={`Period (${r.offset_unit ?? "days"})`}>
                        <Input
                          type="number"
                          min={0}
                          className={mark(rules[r.id].amount !== asStr(r.offset_amount))}
                          value={rules[r.id].amount}
                          onChange={(e) =>
                            setRules({
                              ...rules,
                              [r.id]: { ...rules[r.id], amount: e.target.value },
                            })
                          }
                        />
                      </Field>
                      <Field label="Deemed receipt (business days)">
                        <Input
                          type="number"
                          min={0}
                          className={mark(rules[r.id].delivery !== asStr(r.delivery_amount))}
                          value={rules[r.id].delivery}
                          onChange={(e) =>
                            setRules({
                              ...rules,
                              [r.id]: { ...rules[r.id], delivery: e.target.value },
                            })
                          }
                        />
                      </Field>
                    </div>
                  ))}
              </div>
            </section>
          )}

          {contract.payment_terms.some((p) => payments[p.id]) && (
            <section>
              <h3 className="mb-2 text-sm font-semibold">Payments</h3>
              <div className="space-y-2">
                {contract.payment_terms
                  .filter((p) => payments[p.id])
                  .map((p) => {
                    const v = payments[p.id];
                    const set = (patch: Partial<typeof v>) =>
                      setPayments({ ...payments, [p.id]: { ...v, ...patch } });
                    return (
                      <div key={p.id} className="grid items-end gap-3 sm:grid-cols-4">
                        <p className="text-sm sm:pb-2">{p.description}</p>
                        <Field label={`Amount${p.currency ? ` (${p.currency})` : ""}`}>
                          <Input
                            type="number"
                            step="0.01"
                            className={mark(
                              v.amount !== (p.amount ? String(Number(p.amount)) : ""),
                            )}
                            value={v.amount}
                            onChange={(e) => set({ amount: e.target.value })}
                          />
                        </Field>
                        <Field label="How often">
                          <Select
                            className={mark(v.frequency !== p.frequency)}
                            value={v.frequency}
                            onChange={(e) => set({ frequency: e.target.value })}
                          >
                            {Object.entries(FREQUENCY_LABELS).map(([k, l]) => (
                              <option key={k} value={k}>
                                {l}
                              </option>
                            ))}
                          </Select>
                        </Field>
                        <Field label="First due">
                          <Input
                            type="date"
                            className={mark(v.first_due_date !== asStr(p.first_due_date))}
                            value={v.first_due_date}
                            onChange={(e) => set({ first_due_date: e.target.value })}
                          />
                        </Field>
                      </div>
                    );
                  })}
              </div>
            </section>
          )}

          <section>
            <h3 className="mb-2 text-sm font-semibold">Other terms</h3>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Other party">
                <Input
                  className={mark(changed("counterparty_name"))}
                  value={terms.counterparty_name}
                  onChange={(e) => setT("counterparty_name", e.target.value)}
                />
              </Field>
              <Field label={`Contract value${contract.currency ? ` (${contract.currency})` : ""}`}>
                <Input
                  type="number"
                  step="0.01"
                  className={mark(changed("contract_value"))}
                  value={terms.contract_value}
                  onChange={(e) => setT("contract_value", e.target.value)}
                />
              </Field>
              <Field label="Governing law">
                <Input
                  className={mark(changed("governing_law"))}
                  value={terms.governing_law}
                  onChange={(e) => setT("governing_law", e.target.value)}
                />
              </Field>
              <Field label="How to give notice">
                <Input
                  className={mark(changed("notice_details"))}
                  value={terms.notice_details}
                  onChange={(e) => setT("notice_details", e.target.value)}
                />
              </Field>
            </div>
          </section>
        </div>

        <footer className="border-border flex flex-wrap items-center gap-3 border-t px-5 py-4">
          <Button type="submit" disabled={busy || !meta.title.trim()}>
            {busy ? "Saving…" : "Save amendment"}
          </Button>
          <span className="text-muted text-sm">
            {changeCount === 0
              ? "No term changes yet: you can still record it (e.g. to keep the document)."
              : `${changeCount} ${changeCount === 1 ? "change" : "changes"} to apply.`}
          </span>
          <ErrorText>{error}</ErrorText>
        </footer>
      </form>
    </div>
  );
}

// ---------------------------------------------------------------------------
// List
// ---------------------------------------------------------------------------

function AmendmentItem({
  orgId,
  contract,
  amendment: a,
  canEdit,
}: {
  orgId: string;
  contract: Contract;
  amendment: Schemas["AmendmentOut"];
  canEdit: boolean;
}) {
  const remove = useDeleteAmendment(orgId);
  const attach = useAttachAmendmentDocument(orgId);
  const open = useOpenDocument(orgId);
  const input = useRef<HTMLInputElement>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const lines = describeChanges(a.changes, contract);

  return (
    <li className="py-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="font-medium">{a.title}</p>
          <p className="text-muted text-sm">
            {[
              a.effective_date ? `Effective ${formatIsoDate(a.effective_date)}` : null,
              a.signed_date ? `signed ${formatIsoDate(a.signed_date)}` : null,
            ]
              .filter(Boolean)
              .join(" · ") || "No dates recorded"}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {a.documents.map((d) => (
            <Button
              key={d.id}
              variant="secondary"
              className="h-8 px-2 text-xs"
              onClick={() => open.mutate(d.id)}
            >
              <ExternalLink className="size-3.5" /> {d.filename}
            </Button>
          ))}
          {canEdit && a.documents.length === 0 && (
            <>
              <Button
                variant="ghost"
                className="h-8 px-2 text-xs"
                disabled={attach.isPending}
                onClick={() => input.current?.click()}
              >
                <Upload className="size-3.5" /> Attach document
              </Button>
              <input
                ref={input}
                type="file"
                accept=".pdf,.docx"
                hidden
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) attach.mutate({ amendmentId: a.id, file });
                  e.target.value = "";
                }}
              />
            </>
          )}
          {canEdit && (
            <Button
              variant="ghost"
              className="text-muted h-8 px-2 text-xs"
              aria-label={`Delete ${a.title}`}
              onClick={() => {
                if (!window.confirm(`Delete "${a.title}" and undo its changes?`)) return;
                remove.mutate(a.id, {
                  onSuccess: (res) => {
                    const r = res as Schemas["AmendmentDeleted"];
                    if (r.conflicts.length)
                      setNotice(
                        `Not undone because changed again since: ${r.conflicts.join("; ")}`,
                      );
                  },
                });
              }}
            >
              <Trash2 className="size-3.5" />
            </Button>
          )}
        </div>
      </div>
      {a.description && <p className="mt-1 text-sm">{a.description}</p>}
      {lines.length > 0 && (
        <ul className="bg-background mt-2 space-y-0.5 rounded-md p-2 text-sm">
          {lines.map((l, i) => (
            <li key={i}>{l}</li>
          ))}
        </ul>
      )}
      <ErrorText>{errorMessage(remove.error || attach.error || open.error)}</ErrorText>
      {notice && <p className="text-warning mt-1 text-sm">{notice}</p>}
    </li>
  );
}

export function AmendmentsCard({
  orgId,
  contract,
  canEdit,
}: {
  orgId: string;
  contract: Contract;
  canEdit: boolean;
}) {
  const [adding, setAdding] = useState(false);
  return (
    <Card
      title="Amendments"
      description="Changes agreed after signing. The terms above already include them."
      actions={
        canEdit ? (
          <Button variant="secondary" onClick={() => setAdding(true)}>
            <FilePlus2 className="size-4" /> Record amendment
          </Button>
        ) : null
      }
    >
      {!contract.amendments?.length ? (
        <p className="text-muted text-sm">No amendments recorded.</p>
      ) : (
        <ul className="divide-border divide-y">
          {[...(contract.amendments ?? [])].reverse().map((a) => (
            <AmendmentItem
              key={a.id}
              orgId={orgId}
              contract={contract}
              amendment={a}
              canEdit={canEdit}
            />
          ))}
        </ul>
      )}
      {adding && (
        <AmendmentDialog orgId={orgId} contract={contract} onClose={() => setAdding(false)} />
      )}
    </Card>
  );
}

export function AmendedBadge({ title }: { title?: string }) {
  return <Badge tone="primary">Amended{title ? ` by ${title}` : ""}</Badge>;
}
