"use client";

import { Plus, Trash2 } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { countdownText, daysUntil, formatIsoDate } from "@/components/app/contract-bits";
import { useCurrentOrg } from "@/components/app/use-org";
import { Button, Card, ErrorText, Field, Input, PageHeader, Select } from "@/components/ui";
import {
  useAttachDocument,
  useCreateContractManually,
  useNoticePreview,
  useWorkspace,
  type Schemas,
} from "@/lib/api";
import { FREQUENCY_LABELS, RULE_TYPE_LABELS } from "@/lib/labels";
import { errorMessage } from "@/lib/utils";

type Unit = Schemas["PeriodUnit"];
const UNITS: Unit[] = ["days", "weeks", "months", "years"];

interface PaymentRow {
  description: string;
  amount: string;
  frequency: Schemas["PaymentFrequency"];
  first_due_date: string;
  payment_days: string;
  direction: Schemas["PaymentDirection"];
}

const emptyPayment = (): PaymentRow => ({
  description: "",
  amount: "",
  frequency: "monthly",
  first_due_date: "",
  payment_days: "",
  direction: "payable",
});

const num = (v: string) => (v.trim() === "" ? null : Number(v));
const str = (v: string) => (v.trim() === "" ? null : v.trim());

function PeriodField({
  label,
  amount,
  unit,
  onAmount,
  onUnit,
  hint,
  disabled,
}: {
  label: string;
  amount: string;
  unit: string;
  onAmount: (v: string) => void;
  onUnit: (v: string) => void;
  hint?: string;
  disabled?: boolean;
}) {
  return (
    <Field label={label} hint={hint}>
      <div className="flex gap-2">
        <Input
          type="number"
          min={1}
          className="w-20 shrink-0"
          disabled={disabled}
          value={amount}
          onChange={(e) => onAmount(e.target.value)}
        />
        <Select value={unit} disabled={disabled} onChange={(e) => onUnit(e.target.value)}>
          {UNITS.map((u) => (
            <option key={u}>{u}</option>
          ))}
        </Select>
      </div>
    </Field>
  );
}

export default function NewContractPage() {
  const { workspaceId } = useParams<{ workspaceId: string }>();
  const { orgId, org } = useCurrentOrg();
  const router = useRouter();
  const workspace = useWorkspace(orgId, workspaceId);
  const create = useCreateContractManually(orgId, workspaceId);
  const attach = useAttachDocument(orgId);
  const preview = useNoticePreview();

  const [f, setF] = useState({
    title: "",
    counterparty_name: "",
    contract_type: "",
    effective_date: "",
    initial_term_amount: "12",
    initial_term_unit: "months" as Unit,
    auto_renews: "yes" as "yes" | "no" | "",
    renewal_term_amount: "12",
    renewal_term_unit: "months" as Unit,
    end_date: "",
    notice_type: "non_renewal_notice" as Schemas["DateRuleType"],
    notice_amount: "90",
    notice_unit: "days" as "days" | "weeks" | "months",
    notice_business: false,
    notice_delivery: "",
    governing_law: "",
    holiday_country: "",
    currency: "",
    contract_value: "",
    notice_details: "",
  });
  const [payments, setPayments] = useState<PaymentRow[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const set = (key: keyof typeof f, value: string | boolean) =>
    setF((s) => ({ ...s, [key]: value }));
  const [showPayments, setShowPayments] = useState(false);

  const country = f.holiday_country || workspace.data?.country || org?.default_country || "";
  const noticeUnit: Unit = f.notice_unit;
  const noticeBasis = f.notice_unit === "days" && f.notice_business ? "business" : "calendar";
  const hasTerm = !!f.effective_date && !!f.initial_term_amount;
  const hasNotice = !!f.notice_amount;

  // Live preview of the notice deadline the form will produce.
  const previewKey = JSON.stringify([f, country]);
  const { mutate: runPreview } = preview;
  useEffect(() => {
    if (!hasTerm || !hasNotice || f.notice_type !== "non_renewal_notice") return;
    const timer = setTimeout(() => {
      runPreview({
        effective_date: f.effective_date,
        initial_term: { amount: Number(f.initial_term_amount), unit: f.initial_term_unit },
        renewal_term:
          f.auto_renews === "yes" && f.renewal_term_amount
            ? { amount: Number(f.renewal_term_amount), unit: f.renewal_term_unit }
            : null,
        notice_period: {
          amount: Number(f.notice_amount),
          unit: noticeUnit,
          basis: noticeBasis === "business" ? "business" : "calendar",
        },
        delivery_period: f.notice_delivery
          ? { amount: Number(f.notice_delivery), unit: "days", basis: "business" }
          : null,
        calendar: { country: country || null },
        roll: "preceding",
      });
    }, 400);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [previewKey]);

  const submit = async () => {
    setError(null);
    const body: Schemas["ContractCreate"] = {
      title: f.title.trim(),
      counterparty_name: str(f.counterparty_name),
      contract_type: str(f.contract_type),
      effective_date: str(f.effective_date),
      end_date: str(f.end_date),
      initial_term_amount: num(f.initial_term_amount),
      initial_term_unit: f.initial_term_amount ? f.initial_term_unit : null,
      auto_renews: f.auto_renews === "" ? null : f.auto_renews === "yes",
      renewal_term_amount: f.auto_renews === "yes" ? num(f.renewal_term_amount) : null,
      renewal_term_unit:
        f.auto_renews === "yes" && f.renewal_term_amount ? f.renewal_term_unit : null,
      governing_law: str(f.governing_law),
      holiday_country: str(f.holiday_country),
      currency: str(f.currency),
      contract_value: str(f.contract_value),
      notice_details: str(f.notice_details),
      date_rules: hasNotice
        ? [
            {
              rule_type: f.notice_type,
              label: RULE_TYPE_LABELS[f.notice_type],
              anchor: "term_end",
              offset_amount: Number(f.notice_amount),
              offset_unit: noticeUnit,
              offset_basis: noticeBasis === "business" ? "business" : "calendar",
              direction: "before",
              delivery_amount: num(f.notice_delivery),
            },
          ]
        : [],
      payment_terms: payments
        .filter((p) => p.description.trim())
        .map((p) => ({
          description: p.description.trim(),
          direction: p.direction,
          amount: str(p.amount),
          currency: str(f.currency),
          frequency: p.frequency,
          first_due_date: str(p.first_due_date),
          payment_days: num(p.payment_days),
        })),
    };
    try {
      const contract = (await create.mutateAsync(body)) as Schemas["ContractDetail"];
      if (file) {
        try {
          await attach.mutateAsync({ contractId: contract.id, file });
        } catch (e) {
          // The contract exists; tell the user the file didn't attach.
          setError(`Contract saved, but the file could not be attached: ${errorMessage(e)}`);
          router.push(`/app/${orgId}/contracts/${contract.id}`);
          return;
        }
      }
      router.push(`/app/${orgId}/contracts/${contract.id}`);
    } catch (e) {
      setError(errorMessage(e));
    }
  };

  const busy = create.isPending || attach.isPending;
  const p = preview.data;

  return (
    <>
      <Link
        href={`/app/${orgId}/workspaces/${workspaceId}`}
        className="text-muted text-sm hover:underline"
      >
        ← {workspace.data?.name ?? "Back"}
      </Link>
      <PageHeader
        title="Add a contract"
        description="Only the name is required. Fill in what you know; you can add the rest later."
      />
      <form
        className="grid gap-6 xl:grid-cols-3"
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
      >
        <div className="space-y-6 xl:col-span-2">
          <Card>
            <div className="grid gap-5 sm:grid-cols-2">
              <Field label="Contract name" className="sm:col-span-2">
                <Input
                  required
                  autoFocus
                  value={f.title}
                  placeholder="e.g. Office cleaning agreement"
                  onChange={(e) => set("title", e.target.value)}
                />
              </Field>
              <Field label="Who is it with?" className="sm:col-span-2">
                <Input
                  value={f.counterparty_name}
                  placeholder="e.g. Sparkle Services Ltd"
                  onChange={(e) => set("counterparty_name", e.target.value)}
                />
              </Field>
              <Field label="When did it start?">
                <Input
                  type="date"
                  value={f.effective_date}
                  onChange={(e) => set("effective_date", e.target.value)}
                />
              </Field>
              <PeriodField
                label="How long is the first term?"
                amount={f.initial_term_amount}
                unit={f.initial_term_unit}
                onAmount={(v) => set("initial_term_amount", v)}
                onUnit={(v) => set("initial_term_unit", v)}
              />
              <Field label="Does it renew automatically?">
                <div className="flex gap-2" role="radiogroup">
                  {(
                    [
                      ["yes", "Yes"],
                      ["no", "No"],
                      ["", "Not sure"],
                    ] as const
                  ).map(([value, label]) => (
                    <button
                      key={label}
                      type="button"
                      role="radio"
                      aria-checked={f.auto_renews === value}
                      onClick={() => set("auto_renews", value)}
                      className={
                        f.auto_renews === value
                          ? "border-primary bg-primary/10 text-primary h-9 flex-1 rounded-md border px-3 text-sm font-medium"
                          : "border-border hover:bg-background h-9 flex-1 rounded-md border px-3 text-sm"
                      }
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </Field>
              {f.auto_renews === "yes" ? (
                <PeriodField
                  label="For how long each time?"
                  amount={f.renewal_term_amount}
                  unit={f.renewal_term_unit}
                  onAmount={(v) => set("renewal_term_amount", v)}
                  onUnit={(v) => set("renewal_term_unit", v)}
                />
              ) : (
                <div className="hidden sm:block" />
              )}
              <Field
                label={
                  f.auto_renews === "yes"
                    ? "How much notice to stop it renewing?"
                    : "How much notice to end it?"
                }
                hint="Leave empty if there is no notice period"
              >
                <div className="flex gap-2">
                  <Input
                    type="number"
                    min={0}
                    className="w-20 shrink-0"
                    aria-label="Notice period"
                    value={f.notice_amount}
                    onChange={(e) => set("notice_amount", e.target.value)}
                  />
                  <Select
                    aria-label="Notice period unit"
                    value={f.notice_unit}
                    onChange={(e) => set("notice_unit", e.target.value)}
                  >
                    <option value="days">days</option>
                    <option value="weeks">weeks</option>
                    <option value="months">months</option>
                  </Select>
                </div>
              </Field>
              <Field label="Signed copy (optional)" hint="PDF or Word. You can also add it later.">
                <Input
                  type="file"
                  accept=".pdf,.docx"
                  className="h-auto py-1.5"
                  onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                />
              </Field>
            </div>
          </Card>

          {showPayments || payments.length > 0 ? (
            <Card
              title="Payment reminders"
              description="We'll remind you before each payment or invoice is due."
              actions={
                <Button
                  type="button"
                  variant="secondary"
                  onClick={() => setPayments((rows) => [...rows, emptyPayment()])}
                >
                  <Plus className="size-4" /> Add another
                </Button>
              }
            >
              <div className="space-y-4">
                {payments.map((row, i) => {
                  const update = (patch: Partial<PaymentRow>) =>
                    setPayments((rows) => rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));
                  return (
                    <div
                      key={i}
                      className="border-border grid gap-3 rounded-md border p-3 sm:grid-cols-6"
                    >
                      <Field label="What for" className="sm:col-span-3">
                        <Input
                          required
                          value={row.description}
                          placeholder="e.g. Monthly fee"
                          onChange={(e) => update({ description: e.target.value })}
                        />
                      </Field>
                      <Field label="Amount" className="sm:col-span-2">
                        <Input
                          type="number"
                          step="0.01"
                          value={row.amount}
                          onChange={(e) => update({ amount: e.target.value })}
                        />
                      </Field>
                      <div className="flex items-end justify-end">
                        <Button
                          type="button"
                          variant="ghost"
                          aria-label="Remove payment"
                          onClick={() => {
                            const rest = payments.filter((_, j) => j !== i);
                            setPayments(rest);
                            if (rest.length === 0) setShowPayments(false);
                          }}
                        >
                          <Trash2 className="size-4" />
                        </Button>
                      </div>
                      <Field label="How often" className="sm:col-span-2">
                        <Select
                          value={row.frequency}
                          onChange={(e) =>
                            update({ frequency: e.target.value as Schemas["PaymentFrequency"] })
                          }
                        >
                          {Object.entries(FREQUENCY_LABELS).map(([v, l]) => (
                            <option key={v} value={v}>
                              {l}
                            </option>
                          ))}
                        </Select>
                      </Field>
                      <Field label="First due" className="sm:col-span-2">
                        <Input
                          type="date"
                          value={row.first_due_date}
                          onChange={(e) => update({ first_due_date: e.target.value })}
                        />
                      </Field>
                      <Field label="Who pays" className="sm:col-span-2">
                        <Select
                          value={row.direction}
                          onChange={(e) =>
                            update({ direction: e.target.value as Schemas["PaymentDirection"] })
                          }
                        >
                          <option value="payable">We pay</option>
                          <option value="receivable">We receive</option>
                        </Select>
                      </Field>
                    </div>
                  );
                })}
              </div>
            </Card>
          ) : (
            <button
              type="button"
              className="text-primary flex items-center gap-1 text-sm font-medium hover:underline"
              onClick={() => {
                setShowPayments(true);
                setPayments([emptyPayment()]);
              }}
            >
              <Plus className="size-4" /> Add a payment reminder
            </button>
          )}

          <details className="border-border bg-surface group rounded-lg border">
            <summary className="cursor-pointer px-5 py-4 text-sm font-medium select-none">
              More options{" "}
              <span className="text-muted font-normal">
                — type, fixed end date, business days, governing law, value
              </span>
            </summary>
            <div className="border-border grid gap-4 border-t p-5 sm:grid-cols-2">
              <Field label="Type of contract" hint="e.g. Services, Lease, SaaS, NDA">
                <Input
                  value={f.contract_type}
                  onChange={(e) => set("contract_type", e.target.value)}
                />
              </Field>
              <Field
                label="Fixed end date"
                hint="Only if the contract gives an end date instead of a length"
              >
                <Input
                  type="date"
                  value={f.end_date}
                  onChange={(e) => set("end_date", e.target.value)}
                />
              </Field>
              <Field label="Kind of notice">
                <Select value={f.notice_type} onChange={(e) => set("notice_type", e.target.value)}>
                  <option value="non_renewal_notice">{RULE_TYPE_LABELS.non_renewal_notice}</option>
                  <option value="termination_notice">{RULE_TYPE_LABELS.termination_notice}</option>
                  <option value="option_exercise">{RULE_TYPE_LABELS.option_exercise}</option>
                </Select>
              </Field>
              <Field
                label="How notice must be given"
                hint="e.g. registered post to the registered office"
              >
                <Input
                  value={f.notice_details}
                  onChange={(e) => set("notice_details", e.target.value)}
                />
              </Field>
              <label className="flex items-start gap-2 text-sm sm:col-span-2">
                <input
                  type="checkbox"
                  className="mt-0.5 size-4 accent-[var(--primary)]"
                  checked={f.notice_business}
                  disabled={f.notice_unit !== "days"}
                  onChange={(e) => set("notice_business", e.target.checked)}
                />
                <span>
                  The notice period counts business days only
                  <span className="text-muted block text-xs">
                    Weekends and public holidays are skipped. Only for periods in days.
                  </span>
                </span>
              </label>
              <Field
                label="Notice counts as received after"
                hint="Business days, e.g. 2 if posted notices are deemed received 2 business days later"
              >
                <Input
                  type="number"
                  min={0}
                  value={f.notice_delivery}
                  onChange={(e) => set("notice_delivery", e.target.value)}
                />
              </Field>
              <Field
                label="Public holidays of"
                hint={`Two-letter country code${country && !f.holiday_country ? ` (using ${country})` : ""}`}
              >
                <Input
                  maxLength={2}
                  value={f.holiday_country}
                  onChange={(e) => set("holiday_country", e.target.value.toUpperCase())}
                />
              </Field>
              <Field label="Governing law">
                <Input
                  value={f.governing_law}
                  onChange={(e) => set("governing_law", e.target.value)}
                />
              </Field>
              <Field label="Currency" hint="e.g. EUR, GBP, USD, TRY">
                <Input
                  maxLength={3}
                  value={f.currency}
                  onChange={(e) => set("currency", e.target.value.toUpperCase())}
                />
              </Field>
              <Field label="Contract value">
                <Input
                  type="number"
                  step="0.01"
                  value={f.contract_value}
                  onChange={(e) => set("contract_value", e.target.value)}
                />
              </Field>
            </div>
          </details>
        </div>

        <div className="xl:col-span-1">
          <div className="space-y-4 xl:sticky xl:top-6">
            <Card title="Your deadline">
              {!hasTerm || !hasNotice ? (
                <p className="text-muted text-sm">
                  Enter the start date, length and notice period to see the last day to give notice.
                </p>
              ) : f.notice_type !== "non_renewal_notice" ? (
                <p className="text-muted text-sm">Calculated once the contract is saved.</p>
              ) : preview.error ? (
                <ErrorText>{errorMessage(preview.error)}</ErrorText>
              ) : p ? (
                <div className="space-y-2">
                  <p className="text-muted text-sm">
                    Last day to tell {f.counterparty_name.trim() || "the other party"} you
                    don&rsquo;t want to renew:
                  </p>
                  <p className="text-2xl font-semibold">{formatIsoDate(p.notice_deadline)}</p>
                  <p className="text-muted text-sm">
                    {countdownText(daysUntil(p.notice_deadline))}. We&rsquo;ll remind you well
                    before.
                  </p>
                  <details className="text-muted text-xs">
                    <summary className="cursor-pointer select-none">
                      How was this calculated?
                    </summary>
                    <ol className="bg-background mt-1 space-y-0.5 rounded-md p-2 font-mono">
                      {p.derivation.map((s, i) => (
                        <li key={i}>{s}</li>
                      ))}
                    </ol>
                  </details>
                </div>
              ) : (
                <p className="text-muted text-sm">Calculating…</p>
              )}
            </Card>
            <Button type="submit" className="w-full" disabled={busy || !f.title.trim()}>
              {busy ? "Saving…" : "Save contract"}
            </Button>
            <ErrorText>{error}</ErrorText>
          </div>
        </div>
      </form>
    </>
  );
}
