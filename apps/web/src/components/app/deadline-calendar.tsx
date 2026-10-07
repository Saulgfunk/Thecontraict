"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { Button, ErrorText, Loading } from "@/components/ui";
import { useDeadlines, type Schemas } from "@/lib/api";
import { cn, errorMessage } from "@/lib/utils";

const KIND_STYLE: Record<Schemas["DeadlineKind"], string> = {
  notice: "bg-danger/10 text-danger border-danger/20",
  option: "bg-warning/10 text-warning border-warning/20",
  term_end: "bg-primary/10 text-primary border-primary/20",
  price_review: "bg-success/10 text-success border-success/20",
  payment: "bg-background text-muted border-border",
  other: "bg-background text-foreground border-border",
};
const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const MAX_PER_DAY = 3;

function iso(d: Date) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

/** Monday-start grid covering the whole month. */
function monthGrid(year: number, month: number) {
  const first = new Date(year, month, 1);
  const start = new Date(year, month, 1 - ((first.getDay() + 6) % 7));
  const days: Date[] = [];
  for (let i = 0; i < 42; i++) {
    days.push(new Date(start.getFullYear(), start.getMonth(), start.getDate() + i));
  }
  // Drop a trailing week that lies entirely in the next month.
  return days[35].getMonth() !== month ? days.slice(0, 35) : days;
}

export function DeadlineCalendar({
  orgId,
  workspaceId,
  kind,
}: {
  orgId: string;
  workspaceId?: string;
  kind?: Schemas["DeadlineKind"] | "";
}) {
  const [month, setMonth] = useState(() => {
    const now = new Date();
    return { year: now.getFullYear(), month: now.getMonth() };
  });
  const [todayIso] = useState(() => iso(new Date()));
  const days = monthGrid(month.year, month.month);
  const deadlines = useDeadlines(orgId, {
    workspace_id: workspaceId || undefined,
    from: iso(days[0]),
    to: iso(days[days.length - 1]),
    include_closed: true,
  });
  const byDay = new Map<string, Schemas["DeadlineWithContract"][]>();
  for (const d of deadlines.data ?? []) {
    if (kind && d.kind !== kind) continue;
    byDay.set(d.due_date, [...(byDay.get(d.due_date) ?? []), d]);
  }
  const shift = (delta: number) =>
    setMonth(({ year, month: m }) => {
      const d = new Date(year, m + delta, 1);
      return { year: d.getFullYear(), month: d.getMonth() };
    });
  const title = new Date(month.year, month.month, 1).toLocaleDateString(undefined, {
    month: "long",
    year: "numeric",
  });

  return (
    <div>
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-lg font-semibold">{title}</h3>
        <div className="flex gap-1">
          <Button
            variant="secondary"
            className="h-8 px-2"
            aria-label="Previous month"
            onClick={() => shift(-1)}
          >
            <ChevronLeft className="size-4" />
          </Button>
          <Button
            variant="secondary"
            className="h-8 px-3 text-xs"
            onClick={() => {
              const now = new Date();
              setMonth({ year: now.getFullYear(), month: now.getMonth() });
            }}
          >
            Today
          </Button>
          <Button
            variant="secondary"
            className="h-8 px-2"
            aria-label="Next month"
            onClick={() => shift(1)}
          >
            <ChevronRight className="size-4" />
          </Button>
        </div>
      </div>
      {deadlines.error && <ErrorText>{errorMessage(deadlines.error)}</ErrorText>}
      <div className="overflow-x-auto">
        <div className="border-border grid min-w-[44rem] grid-cols-7 overflow-hidden rounded-md border">
          {WEEKDAYS.map((w) => (
            <div
              key={w}
              className="border-border bg-background text-muted border-b px-2 py-1.5 text-xs font-medium"
            >
              {w}
            </div>
          ))}
          {days.map((day) => {
            const key = iso(day);
            const items = byDay.get(key) ?? [];
            const inMonth = day.getMonth() === month.month;
            return (
              <div
                key={key}
                className={cn(
                  "border-border min-h-24 border-r border-b p-1.5 [&:nth-child(7n)]:border-r-0",
                  !inMonth && "bg-background/60",
                )}
              >
                <div
                  className={cn(
                    "mb-1 flex size-6 items-center justify-center rounded-full text-xs",
                    key === todayIso
                      ? "bg-primary text-primary-foreground font-semibold"
                      : !inMonth && "text-muted",
                  )}
                >
                  {day.getDate()}
                </div>
                <div className="space-y-1">
                  {items.slice(0, MAX_PER_DAY).map((d) => (
                    <Link
                      key={d.id}
                      href={`/app/${orgId}/contracts/${d.contract_id}`}
                      title={`${d.label} – ${d.contract_title}${d.confirmed ? "" : " (unconfirmed)"}`}
                      className={cn(
                        "block truncate rounded border px-1.5 py-0.5 text-[11px] leading-tight hover:opacity-80",
                        KIND_STYLE[d.kind],
                        d.status !== "open" && "line-through opacity-60",
                      )}
                    >
                      {d.label}
                      <span className="opacity-70"> · {d.contract_title}</span>
                    </Link>
                  ))}
                  {items.length > MAX_PER_DAY && (
                    <p className="text-muted px-1 text-[11px]">
                      +{items.length - MAX_PER_DAY} more
                    </p>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>
      {deadlines.isPending && <Loading />}
    </div>
  );
}
