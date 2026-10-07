"use client";

import { Bell } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { useMarkNotificationsRead, useNotifications } from "@/lib/api";
import { cn, formatDateTime } from "@/lib/utils";

export function NotificationBell({ orgId }: { orgId: string }) {
  const notifications = useNotifications(orgId);
  const markRead = useMarkNotificationsRead(orgId);
  const [open, setOpen] = useState(false);
  const panel = useRef<HTMLDivElement>(null);
  const unread = notifications.data?.unread_count ?? 0;

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => {
      if (panel.current && !panel.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  return (
    <div className="relative" ref={panel}>
      <button
        className="text-muted hover:bg-background hover:text-foreground relative rounded-md p-1.5"
        aria-label={`Notifications${unread ? ` (${unread} unread)` : ""}`}
        onClick={() => setOpen((o) => !o)}
      >
        <Bell className="size-5" />
        {unread > 0 && (
          <span className="bg-danger absolute -top-0.5 -right-0.5 flex h-4 min-w-4 items-center justify-center rounded-full px-1 text-[10px] font-semibold text-white">
            {unread > 99 ? "99+" : unread}
          </span>
        )}
      </button>
      {open && (
        <div className="border-border bg-surface absolute top-9 right-0 z-20 w-80 max-w-[calc(100vw-2rem)] rounded-lg border shadow-lg md:right-auto md:left-0">
          <div className="border-border flex items-center justify-between border-b px-4 py-2.5">
            <span className="text-sm font-semibold">Notifications</span>
            {unread > 0 && (
              <button
                className="text-primary text-xs hover:underline"
                onClick={() => markRead.mutate(null)}
              >
                Mark all read
              </button>
            )}
          </div>
          <ul className="divide-border max-h-96 divide-y overflow-y-auto">
            {!notifications.data?.items.length && (
              <li className="text-muted px-4 py-6 text-center text-sm">
                No notifications yet. Deadline reminders appear here.
              </li>
            )}
            {notifications.data?.items.map((n) => (
              <li key={n.id}>
                <Link
                  href={n.link ?? `/app/${orgId}`}
                  onClick={() => {
                    if (!n.read_at) markRead.mutate([n.id]);
                    setOpen(false);
                  }}
                  className={cn(
                    "hover:bg-background block px-4 py-2.5",
                    !n.read_at && "bg-primary/5",
                  )}
                >
                  <span className="flex items-start gap-2">
                    {!n.read_at && (
                      <span className="bg-primary mt-1.5 size-2 shrink-0 rounded-full" />
                    )}
                    <span className="min-w-0">
                      <span className="block text-sm font-medium">{n.title}</span>
                      {n.body && (
                        <span className="text-muted block truncate text-xs">{n.body}</span>
                      )}
                      <span className="text-muted block text-xs">
                        {formatDateTime(n.created_at)}
                      </span>
                    </span>
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
