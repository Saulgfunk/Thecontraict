"use client";

import Link from "next/link";

import { Countdown, formatIsoDate } from "@/components/app/contract-bits";
import { Badge } from "@/components/ui";
import type { Schemas } from "@/lib/api";
import { DEADLINE_KIND_LABELS } from "@/lib/labels";
import { cn } from "@/lib/utils";

type Item = Schemas["DeadlineWithContract"];

function monthKey(iso: string) {
  const [y, m] = iso.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, 1)).toLocaleDateString(undefined, {
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  });
}

export function DeadlineList({
  orgId,
  items,
  grouped = false,
  compact = false,
}: {
  orgId: string;
  items: Item[];
  grouped?: boolean;
  compact?: boolean;
}) {
  const groups: [string, Item[]][] = [];
  for (const d of items) {
    const key = grouped ? monthKey(d.due_date) : "";
    const last = groups.at(-1);
    if (last && last[0] === key) last[1].push(d);
    else groups.push([key, [d]]);
  }
  return (
    <div className="space-y-5">
      {groups.map(([month, list]) => (
        <section key={month || "all"}>
          {month && <h3 className="text-muted mb-1 text-sm font-semibold">{month}</h3>}
          <ul className="divide-border divide-y">
            {list.map((d) => {
              const closed = d.status !== "open";
              return (
                <li key={d.id}>
                  <Link
                    href={`/app/${orgId}/contracts/${d.contract_id}`}
                    className="hover:text-primary flex flex-wrap items-center justify-between gap-2 py-2.5"
                  >
                    <span className={cn("min-w-0", closed && "text-muted line-through")}>
                      <span className="block font-medium">{d.label}</span>
                      <span className="text-muted block truncate text-xs">
                        {d.contract_title}
                        {d.counterparty_name ? ` · ${d.counterparty_name}` : ""}
                        {compact ? "" : ` · ${d.workspace_name}`}
                      </span>
                    </span>
                    <span className="flex flex-wrap items-center gap-2 text-sm">
                      {!compact && <Badge>{DEADLINE_KIND_LABELS[d.kind]}</Badge>}
                      {!d.confirmed && <Badge tone="warning">Unconfirmed</Badge>}
                      <span className="text-muted">{formatIsoDate(d.due_date)}</span>
                      {closed ? <Badge>Done</Badge> : <Countdown date={d.due_date} />}
                    </span>
                  </Link>
                </li>
              );
            })}
          </ul>
        </section>
      ))}
    </div>
  );
}
