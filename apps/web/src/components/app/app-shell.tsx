"use client";

import { Building2, CalendarClock, FileText, Home, LogOut, Settings } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";

import { Logo } from "@/components/app/logo";
import { NotificationBell } from "@/components/app/notification-bell";
import { Waiting } from "@/components/app/waiting";
import { ErrorText, Select } from "@/components/ui";
import { useMe } from "@/lib/api";
import { useAuthState } from "@/lib/auth";
import { LAST_ORG_KEY } from "@/lib/config";
import { cn, errorMessage } from "@/lib/utils";

export function AppShell({ orgId, children }: { orgId: string; children: React.ReactNode }) {
  const me = useMe();
  const auth = useAuthState();
  const router = useRouter();
  const pathname = usePathname();
  const current = me.data?.organizations.find((o) => o.organization.id === orgId);

  useEffect(() => {
    if (!current) return;
    try {
      window.localStorage.setItem(LAST_ORG_KEY, orgId);
    } catch {}
  }, [current, orgId]);

  if (me.isPending) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Waiting />
      </div>
    );
  }
  if (me.error || !current) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-3">
        <ErrorText>{me.error ? errorMessage(me.error) : "Organization not found."}</ErrorText>
        <Link href="/app" className="text-primary text-sm hover:underline">
          Back
        </Link>
      </div>
    );
  }

  const base = `/app/${orgId}`;
  const nav = [
    { href: base, label: "Home", icon: Home, match: [] as string[], exact: true },
    {
      href: `${base}/contracts`,
      label: "Contracts",
      icon: FileText,
      match: [`${base}/workspaces`],
    },
    { href: `${base}/deadlines`, label: "Deadlines", icon: CalendarClock, match: [] },
    {
      href: `${base}/settings`,
      label: "Settings",
      icon: Settings,
      // Team, activity log and the calculator live under Settings.
      match: [`${base}/members`, `${base}/audit`, `${base}/tools`],
    },
  ];

  const email = auth.email ?? "";
  const initials = (email.split("@")[0] || "?")
    .split(/[._-]/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase())
    .join("");

  return (
    <div className="flex min-h-screen flex-col md:flex-row">
      <aside className="bg-sidebar text-sidebar-foreground flex flex-col gap-6 p-4 md:sticky md:top-0 md:h-screen md:w-64 md:shrink-0 md:p-5">
        <div className="flex items-center justify-between">
          <Link href={base} className="rounded-lg">
            <Logo light />
          </Link>
          <NotificationBell orgId={orgId} />
        </div>

        {me.data.organizations.length > 1 ? (
          <Select
            aria-label="Switch organization"
            className="border-sidebar-2 bg-sidebar-2 text-sidebar-foreground hover:border-sidebar-muted/40 h-9"
            value={orgId}
            onChange={(e) =>
              router.push(e.target.value === "__new" ? "/app/new" : `/app/${e.target.value}`)
            }
          >
            {me.data.organizations.map((o) => (
              <option key={o.organization.id} value={o.organization.id}>
                {o.organization.name}
              </option>
            ))}
            <option value="__new">+ New organization…</option>
          </Select>
        ) : (
          <p className="bg-sidebar-2 flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium">
            <Building2 className="text-sidebar-muted size-4" />
            <span className="truncate">{current.organization.name}</span>
          </p>
        )}

        <nav className="flex flex-row flex-wrap gap-1 md:flex-col">
          {nav.map(({ href, label, icon: Icon, exact, match }) => {
            const active = exact
              ? pathname === href
              : [href, ...match].some((p) => pathname.startsWith(p));
            return (
              <Link
                key={href}
                href={href}
                className={cn(
                  "relative flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors",
                  active
                    ? "bg-white/10 font-medium text-white"
                    : "text-sidebar-muted hover:bg-white/5 hover:text-white",
                )}
              >
                {active && (
                  <span className="bg-accent absolute top-2 bottom-2 left-0 hidden w-0.5 rounded-full md:block" />
                )}
                <Icon className="size-4" />
                {label}
              </Link>
            );
          })}
        </nav>

        <div className="mt-auto flex items-center gap-3 border-t border-white/10 pt-4 text-sm">
          <span className="bg-accent/20 text-accent flex size-8 shrink-0 items-center justify-center rounded-full text-xs font-semibold">
            {initials}
          </span>
          <span className="text-sidebar-muted min-w-0 flex-1 truncate" title={email}>
            {email}
          </span>
          <button
            onClick={() => auth.signOut()}
            className="text-sidebar-muted rounded p-1 hover:text-white"
            aria-label="Sign out"
            title="Sign out"
          >
            <LogOut className="size-4" />
          </button>
        </div>
      </aside>
      <main className="min-w-0 flex-1 px-4 py-6 sm:px-8 md:py-10 lg:px-12">
        <div className="mx-auto max-w-7xl">{children}</div>
      </main>
    </div>
  );
}
