"use client";

import { Building2, CalendarClock, FileText, Home, LogOut, Settings } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";

import { NotificationBell } from "@/components/app/notification-bell";
import { ErrorText, Loading, Select } from "@/components/ui";
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
        <Loading />
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

  return (
    <div className="flex min-h-screen flex-col md:flex-row">
      <aside className="border-border bg-surface flex flex-col gap-6 border-b p-4 md:w-64 md:border-r md:border-b-0">
        <div className="flex items-center justify-between">
          <Link href={base} className="px-2 text-lg font-semibold">
            TheContr<span className="text-primary">AI</span>ct
          </Link>
          <NotificationBell orgId={orgId} />
        </div>

        {me.data.organizations.length > 1 ? (
          <div className="space-y-1">
            <div className="text-muted flex items-center gap-2 px-2 text-xs font-medium tracking-wide uppercase">
              <Building2 className="size-3.5" /> Organization
            </div>
            <Select
              aria-label="Switch organization"
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
          </div>
        ) : (
          <p className="flex items-center gap-2 px-2 text-sm font-medium">
            <Building2 className="text-muted size-4" /> {current.organization.name}
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
                  "flex items-center gap-2 rounded-md px-2 py-1.5 text-sm",
                  active ? "bg-primary/10 text-primary font-medium" : "hover:bg-background",
                )}
              >
                <Icon className="size-4" />
                {label}
              </Link>
            );
          })}
        </nav>

        <div className="border-border mt-auto flex items-center justify-between gap-2 border-t px-2 pt-4 text-sm">
          <span className="text-muted truncate" title={auth.email ?? ""}>
            {auth.email}
          </span>
          <button
            onClick={() => auth.signOut()}
            className="text-muted hover:text-foreground rounded p-1"
            aria-label="Sign out"
            title="Sign out"
          >
            <LogOut className="size-4" />
          </button>
        </div>
      </aside>
      <main className="min-w-0 flex-1 p-6 md:p-10">{children}</main>
    </div>
  );
}
