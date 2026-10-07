"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { useCurrentOrg } from "@/components/app/use-org";
import { cn } from "@/lib/utils";

/** Heading and tabs shared by the pages under Settings. */
export function SettingsHeader({ description }: { description: string }) {
  const { orgId, isAdmin } = useCurrentOrg();
  const pathname = usePathname();
  const base = `/app/${orgId}`;
  const tabs = [
    { href: `${base}/settings`, label: "Reminders" },
    { href: `${base}/members`, label: "Team" },
    { href: `${base}/tools/deadline-calculator`, label: "Deadline calculator" },
    ...(isAdmin ? [{ href: `${base}/audit`, label: "Activity log" }] : []),
  ];
  return (
    <div className="mb-6">
      <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
      <nav className="border-border mt-4 flex flex-wrap items-center gap-x-1 border-b">
        {tabs.map((t) => (
          <Link
            key={t.href}
            href={t.href}
            className={cn(
              "-mb-px border-b-2 px-3 py-2 text-sm",
              pathname.startsWith(t.href)
                ? "border-primary text-primary font-medium"
                : "text-muted hover:text-foreground border-transparent",
            )}
          >
            {t.label}
          </Link>
        ))}
        <Link
          href="/app/new"
          className="text-muted hover:text-foreground ml-auto px-3 py-2 text-sm"
        >
          + New organization
        </Link>
      </nav>
      <p className="text-muted mt-3 text-sm">{description}</p>
    </div>
  );
}
