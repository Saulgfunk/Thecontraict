"use client";

import { Badge } from "@/components/ui";
import type { Schemas } from "@/lib/api";
import { ANCHOR_LABELS } from "@/lib/labels";
import { cn } from "@/lib/utils";

export function daysUntil(isoDate: string): number {
  const [y, m, d] = isoDate.split("-").map(Number);
  const due = Date.UTC(y, m - 1, d);
  const now = new Date();
  const today = Date.UTC(now.getFullYear(), now.getMonth(), now.getDate());
  return Math.round((due - today) / 86_400_000);
}

export function countdownText(days: number): string {
  if (days === 0) return "Today";
  if (days === 1) return "Tomorrow";
  if (days === -1) return "Yesterday";
  const abs = Math.abs(days);
  let text: string;
  if (abs < 14) text = `${abs} days`;
  else if (abs < 60) text = `${Math.round(abs / 7)} weeks`;
  else text = `${(abs / 30.44).toFixed(abs < 365 ? 0 : 1)} months`;
  if (abs >= 14) text = `${text} (${abs} days)`;
  return days < 0 ? `${text} ago` : `in ${text}`;
}

export function Countdown({ date, closed }: { date: string; closed?: boolean }) {
  const days = daysUntil(date);
  const tone = closed
    ? "neutral"
    : days < 0
      ? "danger"
      : days <= 30
        ? "danger"
        : days <= 90
          ? "warning"
          : "success";
  return <Badge tone={tone}>{countdownText(days)}</Badge>;
}

/** Format an ISO date (YYYY-MM-DD) without time-zone shifts. */
export function formatIsoDate(isoDate: string | null | undefined) {
  if (!isoDate) return "—";
  const [y, m, d] = isoDate.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
}

export function formatPeriod(amount: number | null | undefined, unit: string | null | undefined) {
  if (amount == null || !unit) return "—";
  return `${amount} ${amount === 1 ? unit.replace(/s$/, "") : unit}`;
}

export function describeRule(rule: Schemas["DateRuleOut"]) {
  const anchor =
    rule.anchor === "fixed_date"
      ? formatIsoDate(rule.fixed_date)
      : `the ${ANCHOR_LABELS[rule.anchor]}`;
  let text: string;
  if (!rule.offset_amount) text = `On ${anchor}`;
  else {
    const one = rule.offset_amount === 1;
    const base = (rule.offset_unit ?? "days").replace(/s$/, "") + (one ? "" : "s");
    const unit =
      rule.offset_unit === "days"
        ? `${rule.offset_basis === "business" ? "business" : "calendar"} ${base}`
        : base;
    text = `${rule.offset_amount} ${unit} ${rule.direction} ${anchor}`;
  }
  if (rule.delivery_amount) {
    text += `; notices deemed received ${rule.delivery_amount} business days after sending`;
  }
  return text;
}

const REVIEW: Record<
  Schemas["ReviewStatus"],
  { label: string; tone: "warning" | "success" | "primary" | "neutral" }
> = {
  ai_suggested: { label: "AI suggested", tone: "warning" },
  confirmed: { label: "Confirmed", tone: "success" },
  edited: { label: "Edited", tone: "primary" },
  rejected: { label: "Rejected", tone: "neutral" },
};

export function ReviewBadge({ status }: { status: Schemas["ReviewStatus"] | string }) {
  if (status === "manual") return <Badge tone="neutral">Entered manually</Badge>;
  const r = REVIEW[status as Schemas["ReviewStatus"]] ?? REVIEW.ai_suggested;
  return <Badge tone={r.tone}>{r.label}</Badge>;
}

export function Confidence({ value }: { value: number | null | undefined }) {
  if (value == null) return null;
  const pct = Math.round(value * 100);
  return (
    <span
      className={cn("text-xs", pct < 70 ? "text-warning font-medium" : "text-muted")}
      title="How unambiguous the contract wording is"
    >
      {pct}% confidence
    </span>
  );
}

export function SourceRefs({
  refs,
  quote,
  onSelect,
}: {
  refs: string[];
  quote?: string | null;
  onSelect: (refs: string[]) => void;
}) {
  if (!refs.length && !quote) return null;
  return (
    <div className="text-muted mt-1 flex flex-wrap items-baseline gap-x-2 gap-y-1 text-xs">
      {refs.length > 0 && (
        <button
          type="button"
          className="text-primary font-medium hover:underline"
          onClick={() => onSelect(refs)}
        >
          Source: {refs.join(", ")}
        </button>
      )}
      {quote && <q className="italic">{quote}</q>}
    </div>
  );
}

export function formatMoney(amount: string | number | null | undefined, currency: string | null) {
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
