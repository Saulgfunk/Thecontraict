"use client";

import { Check } from "lucide-react";
import { useState } from "react";

import { AmendedBadge } from "@/components/app/amendments";
import { Confidence, ReviewBadge, SourceRefs } from "@/components/app/contract-bits";
import { Button, Card, ErrorText, Field, Input, Select } from "@/components/ui";
import { useConfirmTerms, useUpdateContract, type Schemas } from "@/lib/api";
import { errorMessage } from "@/lib/utils";

type Contract = Schemas["ContractDetail"];
type Unit = Schemas["PeriodUnit"];

interface FormState {
  title: string;
  counterparty_name: string;
  effective_date: string;
  end_date: string;
  initial_term_amount: string;
  initial_term_unit: Unit | "";
  auto_renews: "yes" | "no" | "";
  renewal_term_amount: string;
  renewal_term_unit: Unit | "";
  governing_law: string;
  holiday_country: string;
  currency: string;
  contract_value: string;
  notice_details: string;
}

function toForm(c: Contract): FormState {
  return {
    title: c.title,
    counterparty_name: c.counterparty_name ?? "",
    effective_date: c.effective_date ?? "",
    end_date: c.end_date ?? "",
    initial_term_amount: c.initial_term_amount?.toString() ?? "",
    initial_term_unit: c.initial_term_unit ?? "",
    auto_renews: c.auto_renews == null ? "" : c.auto_renews ? "yes" : "no",
    renewal_term_amount: c.renewal_term_amount?.toString() ?? "",
    renewal_term_unit: c.renewal_term_unit ?? "",
    governing_law: c.governing_law ?? "",
    holiday_country: c.holiday_country ?? "",
    currency: c.currency ?? "",
    contract_value: c.contract_value?.toString() ?? "",
    notice_details: c.notice_details ?? "",
  };
}

function toUpdate(form: FormState, original: FormState): Schemas["ContractUpdate"] {
  const out: Record<string, unknown> = {};
  const nullable = (v: string) => (v.trim() === "" ? null : v.trim());
  for (const key of Object.keys(form) as (keyof FormState)[]) {
    if (form[key] === original[key]) continue;
    const v = form[key];
    if (key === "auto_renews") out[key] = v === "" ? null : v === "yes";
    else if (key.endsWith("_amount")) out[key] = v === "" ? null : Number(v);
    else if (key === "title") out[key] = v;
    else out[key] = nullable(v);
  }
  return out as Schemas["ContractUpdate"];
}

const UNITS: Unit[] = ["days", "weeks", "months", "years"];

export function ContractTerms({
  orgId,
  contract,
  canEdit,
  onSelectRefs,
}: {
  orgId: string;
  contract: Contract;
  canEdit: boolean;
  onSelectRefs: (refs: string[]) => void;
}) {
  const update = useUpdateContract(orgId, contract.id);
  const confirm = useConfirmTerms(orgId, contract.id);
  const original = toForm(contract);
  const [form, setForm] = useState<FormState>(original);
  const [baseline, setBaseline] = useState(contract.updated_at);
  // Reset the form when the contract changes on the server (e.g. after re-analysis).
  const serverVersion = contract.updated_at;
  if (serverVersion !== baseline) {
    setBaseline(serverVersion);
    setForm(original);
  }
  const changes = toUpdate(form, original);
  const dirty = Object.keys(changes).length > 0;
  const sources = contract.field_sources as Record<
    string,
    {
      clause_refs?: string[];
      quote?: string;
      confidence?: number;
      status?: string;
      amendment_title?: string;
    }
  >;
  const set = <K extends keyof FormState>(key: K, value: FormState[K]) =>
    setForm((f) => ({ ...f, [key]: value }));

  const meta = (field: string) => {
    const s = sources[field];
    if (!s) return null;
    return (
      <div className="mt-1 space-y-0.5">
        <div className="flex items-center gap-2">
          {s.status === "amended" ? (
            <AmendedBadge title={s.amendment_title} />
          ) : (
            <ReviewBadge status={s.status ?? "ai_suggested"} />
          )}
          {s.status === "ai_suggested" && <Confidence value={s.confidence} />}
        </div>
        <SourceRefs refs={s.clause_refs ?? []} quote={s.quote} onSelect={onSelectRefs} />
      </div>
    );
  };

  const disabled = !canEdit;
  const unconfirmed = Object.values(sources).some((s) => s.status === "ai_suggested");

  return (
    <Card
      title="Key terms"
      description={
        contract.reviewed_at
          ? "Reviewed. Changes recalculate the deadlines."
          : "Check these against the contract, correct anything wrong, then confirm."
      }
      actions={
        canEdit && (unconfirmed || !contract.reviewed_at) ? (
          <Button
            onClick={() => confirm.mutate()}
            disabled={confirm.isPending || dirty}
            title={dirty ? "Save your changes first" : undefined}
          >
            <Check className="size-4" /> Confirm terms
          </Button>
        ) : null
      }
    >
      <form
        className="grid gap-x-4 gap-y-5 sm:grid-cols-2"
        onSubmit={(e) => {
          e.preventDefault();
          update.mutate(changes);
        }}
      >
        <Field label="Title" className="sm:col-span-2">
          <Input
            disabled={disabled}
            value={form.title}
            onChange={(e) => set("title", e.target.value)}
          />
        </Field>
        <div>
          <Field label="Counterparty">
            <Input
              disabled={disabled}
              value={form.counterparty_name}
              onChange={(e) => set("counterparty_name", e.target.value)}
            />
          </Field>
        </div>
        <div>
          <Field label="Governing law">
            <Input
              disabled={disabled}
              value={form.governing_law}
              onChange={(e) => set("governing_law", e.target.value)}
            />
          </Field>
          {meta("governing_law")}
        </div>
        <div>
          <Field label="Effective date">
            <Input
              type="date"
              disabled={disabled}
              value={form.effective_date}
              onChange={(e) => set("effective_date", e.target.value)}
            />
          </Field>
          {meta("effective_date")}
        </div>
        <div>
          <Field label="Initial term">
            <div className="flex gap-2">
              <Input
                type="number"
                min={1}
                className="w-20 shrink-0"
                disabled={disabled}
                value={form.initial_term_amount}
                onChange={(e) => set("initial_term_amount", e.target.value)}
              />
              <Select
                disabled={disabled}
                value={form.initial_term_unit}
                onChange={(e) => set("initial_term_unit", e.target.value as Unit | "")}
              >
                <option value="">—</option>
                {UNITS.map((u) => (
                  <option key={u}>{u}</option>
                ))}
              </Select>
            </div>
          </Field>
          {meta("initial_term")}
        </div>
        <div>
          <Field label="Renews automatically?">
            <Select
              disabled={disabled}
              value={form.auto_renews}
              onChange={(e) => set("auto_renews", e.target.value as FormState["auto_renews"])}
            >
              <option value="">Unknown</option>
              <option value="yes">Yes</option>
              <option value="no">No</option>
            </Select>
          </Field>
          {meta("auto_renews")}
        </div>
        <div>
          <Field label="Renewal term">
            <div className="flex gap-2">
              <Input
                type="number"
                min={1}
                className="w-20 shrink-0"
                disabled={disabled || form.auto_renews !== "yes"}
                value={form.renewal_term_amount}
                onChange={(e) => set("renewal_term_amount", e.target.value)}
              />
              <Select
                disabled={disabled || form.auto_renews !== "yes"}
                value={form.renewal_term_unit}
                onChange={(e) => set("renewal_term_unit", e.target.value as Unit | "")}
              >
                <option value="">—</option>
                {UNITS.map((u) => (
                  <option key={u}>{u}</option>
                ))}
              </Select>
            </div>
          </Field>
          {meta("renewal_term")}
        </div>
        <div>
          <Field label="Fixed end date" hint="Only if the contract states one">
            <Input
              type="date"
              disabled={disabled}
              value={form.end_date}
              onChange={(e) => set("end_date", e.target.value)}
            />
          </Field>
          {meta("end_date")}
        </div>
        <div>
          <Field label="Contract value">
            <div className="flex gap-2">
              <Input
                className="w-20 shrink-0"
                placeholder="EUR"
                maxLength={3}
                disabled={disabled}
                value={form.currency}
                onChange={(e) => set("currency", e.target.value.toUpperCase())}
              />
              <Input
                type="number"
                step="0.01"
                disabled={disabled}
                value={form.contract_value}
                onChange={(e) => set("contract_value", e.target.value)}
              />
            </div>
          </Field>
          {meta("contract_value")}
        </div>
        <div>
          <Field
            label="Holiday calendar"
            hint="Country code for business days; defaults to the workspace's country"
          >
            <Input
              maxLength={2}
              disabled={disabled}
              value={form.holiday_country}
              onChange={(e) => set("holiday_country", e.target.value.toUpperCase())}
            />
          </Field>
        </div>
        <div className="sm:col-span-2">
          <Field label="How to give notice">
            <Input
              disabled={disabled}
              value={form.notice_details}
              onChange={(e) => set("notice_details", e.target.value)}
            />
          </Field>
          {meta("notice_details")}
        </div>
        {canEdit && (
          <div className="flex items-center gap-3 sm:col-span-2">
            <Button type="submit" variant="secondary" disabled={!dirty || update.isPending}>
              {update.isPending ? "Saving…" : "Save changes"}
            </Button>
            {dirty && (
              <Button type="button" variant="ghost" onClick={() => setForm(original)}>
                Discard
              </Button>
            )}
            <ErrorText>{errorMessage(update.error || confirm.error)}</ErrorText>
          </div>
        )}
      </form>
    </Card>
  );
}
