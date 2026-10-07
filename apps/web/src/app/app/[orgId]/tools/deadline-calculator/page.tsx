"use client";

import { useState } from "react";

import { SettingsHeader } from "@/components/app/settings-tabs";
import { useCurrentOrg } from "@/components/app/use-org";
import { Badge, Button, Card, ErrorText, Field, Input, Select } from "@/components/ui";
import { useNoticePreview, type Schemas } from "@/lib/api";
import { errorMessage, formatDate } from "@/lib/utils";

type Unit = Schemas["Unit"];
type Basis = Schemas["DayBasis"];

function PeriodInput({
  label,
  amount,
  unit,
  basis,
  onChange,
  allowBusiness = true,
}: {
  label: string;
  amount: string;
  unit: Unit;
  basis?: Basis;
  onChange: (next: { amount: string; unit: Unit; basis?: Basis }) => void;
  allowBusiness?: boolean;
}) {
  const value = basis === "business" ? "business_days" : unit;
  return (
    <Field label={label}>
      <div className="flex gap-2">
        <Input
          type="number"
          min={0}
          className="w-20 shrink-0"
          value={amount}
          onChange={(e) => onChange({ amount: e.target.value, unit, basis })}
        />
        <Select
          value={value}
          onChange={(e) =>
            e.target.value === "business_days"
              ? onChange({ amount, unit: "days", basis: "business" })
              : onChange({ amount, unit: e.target.value as Unit, basis: "calendar" })
          }
        >
          <option value="days">calendar days</option>
          {allowBusiness && <option value="business_days">business days</option>}
          <option value="weeks">weeks</option>
          <option value="months">months</option>
          <option value="years">years</option>
        </Select>
      </div>
    </Field>
  );
}

function daysLeftTone(days: number) {
  if (days < 0) return "danger" as const;
  if (days <= 30) return "danger" as const;
  if (days <= 90) return "warning" as const;
  return "success" as const;
}

function humanize(days: number) {
  const abs = Math.abs(days);
  const parts = [`${abs} day${abs === 1 ? "" : "s"}`];
  if (abs >= 14) parts.push(`≈ ${Math.round(abs / 7)} weeks`);
  if (abs >= 60) parts.push(`≈ ${(abs / 30.44).toFixed(1)} months`);
  return days < 0 ? `${parts.join(" · ")} ago` : `${parts.join(" · ")} left`;
}

export default function DeadlineCalculatorPage() {
  const { org } = useCurrentOrg();
  const preview = useNoticePreview();
  const [effective, setEffective] = useState("2025-01-01");
  const [initial, setInitial] = useState({ amount: "24", unit: "months" as Unit });
  const [autoRenews, setAutoRenews] = useState(true);
  const [renewal, setRenewal] = useState({ amount: "12", unit: "months" as Unit });
  const [notice, setNotice] = useState<{ amount: string; unit: Unit; basis?: Basis }>({
    amount: "90",
    unit: "days",
    basis: "calendar",
  });
  const [delivery, setDelivery] = useState<{ amount: string; unit: Unit; basis?: Basis }>({
    amount: "0",
    unit: "days",
    basis: "business",
  });
  const [country, setCountry] = useState(org?.default_country ?? "");
  const [subdivision, setSubdivision] = useState("");
  const [roll, setRoll] = useState<Schemas["Roll"]>("preceding");

  const submit = () =>
    preview.mutate({
      effective_date: effective,
      initial_term: { amount: Number(initial.amount), unit: initial.unit },
      renewal_term: autoRenews ? { amount: Number(renewal.amount), unit: renewal.unit } : null,
      notice_period: { amount: Number(notice.amount), unit: notice.unit, basis: notice.basis },
      delivery_period: Number(delivery.amount)
        ? { amount: Number(delivery.amount), unit: delivery.unit, basis: delivery.basis }
        : null,
      calendar: { country: country || null, subdivision: subdivision || null },
      roll,
    });

  const result = preview.data;

  return (
    <>
      <SettingsHeader description="Work out the last day to send a notice of non-renewal, without saving a contract." />
      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Contract terms">
          <form
            className="grid gap-4 sm:grid-cols-2"
            onSubmit={(e) => {
              e.preventDefault();
              submit();
            }}
          >
            <Field label="Effective date">
              <Input
                type="date"
                required
                value={effective}
                onChange={(e) => setEffective(e.target.value)}
              />
            </Field>
            <PeriodInput
              label="Initial term"
              amount={initial.amount}
              unit={initial.unit}
              allowBusiness={false}
              onChange={(v) => setInitial({ amount: v.amount, unit: v.unit })}
            />
            <Field label="Renews automatically?">
              <Select
                value={autoRenews ? "yes" : "no"}
                onChange={(e) => setAutoRenews(e.target.value === "yes")}
              >
                <option value="yes">Yes</option>
                <option value="no">No</option>
              </Select>
            </Field>
            {autoRenews ? (
              <PeriodInput
                label="Renewal term"
                amount={renewal.amount}
                unit={renewal.unit}
                allowBusiness={false}
                onChange={(v) => setRenewal({ amount: v.amount, unit: v.unit })}
              />
            ) : (
              <div />
            )}
            <PeriodInput label="Notice period (before term end)" {...notice} onChange={setNotice} />
            <PeriodInput label="Deemed receipt delay" {...delivery} onChange={setDelivery} />
            <Field label="Holiday country" hint="Two-letter code, e.g. GB, US, DE, TR">
              <Input
                value={country}
                maxLength={2}
                onChange={(e) => setCountry(e.target.value.toUpperCase())}
              />
            </Field>
            <Field label="Region (optional)" hint="e.g. ENG, NY, BY">
              <Input
                value={subdivision}
                onChange={(e) => setSubdivision(e.target.value.toUpperCase())}
              />
            </Field>
            <Field label="If the deadline falls on a weekend or holiday" className="sm:col-span-2">
              <Select value={roll} onChange={(e) => setRoll(e.target.value as Schemas["Roll"])}>
                <option value="preceding">Move to the previous business day (safest)</option>
                <option value="following">Move to the next business day</option>
                <option value="none">Don&apos;t adjust</option>
              </Select>
            </Field>
            <div className="sm:col-span-2">
              <Button type="submit" disabled={preview.isPending}>
                Calculate
              </Button>
            </div>
          </form>
        </Card>

        <Card title="Result">
          {preview.error ? (
            <ErrorText>{errorMessage(preview.error)}</ErrorText>
          ) : !result ? (
            <p className="text-muted text-sm">Enter the contract terms and press Calculate.</p>
          ) : (
            <div className="space-y-5">
              <div>
                <p className="text-muted text-sm">Last day to give notice</p>
                <p className="text-3xl font-semibold">{formatDate(result.notice_deadline)}</p>
                <div className="mt-2">
                  <Badge tone={daysLeftTone(result.days_left)}>{humanize(result.days_left)}</Badge>
                </div>
              </div>
              <div className="text-sm">
                <p className="text-muted">Applies to</p>
                <p>
                  {result.term.number === 1
                    ? "Initial term"
                    : `Renewal term ${result.term.number - 1}`}
                  : {formatDate(result.term.start)} – {formatDate(result.term.end)}
                </p>
              </div>
              <div>
                <p className="text-muted mb-2 text-sm">How this was calculated</p>
                <ol className="border-border bg-background space-y-1 rounded-md border p-3 font-mono text-xs">
                  {result.derivation.map((step, i) => (
                    <li key={i}>{step}</li>
                  ))}
                </ol>
              </div>
            </div>
          )}
        </Card>
      </div>
    </>
  );
}
