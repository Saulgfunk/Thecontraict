"use client";

import { CalendarPlus, Copy } from "lucide-react";
import { useState } from "react";

import { useCurrentOrg } from "@/components/app/use-org";
import { Button, Card, ErrorText, Field, Input, Loading, PageHeader } from "@/components/ui";
import {
  useCalendarFeed,
  useCreateCalendarFeed,
  useDeleteCalendarFeed,
  usePreferences,
  useReminderSettings,
  useUpdatePreferences,
  useUpdateReminderSettings,
  type Schemas,
} from "@/lib/api";
import { DEADLINE_KIND_LABELS } from "@/lib/labels";
import { errorMessage, formatDateTime } from "@/lib/utils";

function Toggle({
  label,
  description,
  checked,
  onChange,
  disabled,
}: {
  label: string;
  description: string;
  checked: boolean;
  onChange: (v: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <label className="flex cursor-pointer items-start gap-3 py-2">
      <input
        type="checkbox"
        className="mt-1 size-4 accent-[var(--primary)]"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span>
        <span className="block text-sm font-medium">{label}</span>
        <span className="text-muted block text-sm">{description}</span>
      </span>
    </label>
  );
}

function MyNotifications({ orgId }: { orgId: string }) {
  const prefs = usePreferences(orgId);
  const update = useUpdatePreferences(orgId);
  return (
    <Card title="My notifications" description="Reminders always appear in the app as well.">
      {prefs.isPending ? (
        <Loading />
      ) : prefs.error ? (
        <ErrorText>{errorMessage(prefs.error)}</ErrorText>
      ) : (
        <>
          <Toggle
            label="Email reminders"
            description="Emails before deadlines of contracts you own."
            checked={prefs.data.email_reminders}
            disabled={update.isPending}
            onChange={(v) => update.mutate({ email_reminders: v })}
          />
          <Toggle
            label="Weekly digest"
            description="A Monday email with the next 30 days, overdue items and contracts to review."
            checked={prefs.data.weekly_digest}
            disabled={update.isPending}
            onChange={(v) => update.mutate({ weekly_digest: v })}
          />
          <ErrorText>{errorMessage(update.error)}</ErrorText>
        </>
      )}
    </Card>
  );
}

function CalendarFeedCard({ orgId }: { orgId: string }) {
  const feed = useCalendarFeed(orgId);
  const create = useCreateCalendarFeed(orgId);
  const remove = useDeleteCalendarFeed(orgId);
  const [url, setUrl] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  return (
    <Card
      title="Calendar"
      description="Subscribe in Google Calendar, Outlook or Apple Calendar to see your deadlines there. The link is private: anyone with it can see your deadlines."
    >
      {feed.isPending ? (
        <Loading />
      ) : (
        <div className="space-y-3">
          {url && (
            <div className="border-border bg-background space-y-2 rounded-md border p-3">
              <p className="text-sm font-medium">Your calendar link (shown only once)</p>
              <div className="flex gap-2">
                <Input readOnly value={url} onFocus={(e) => e.target.select()} />
                <Button
                  variant="secondary"
                  onClick={async () => {
                    await navigator.clipboard.writeText(url);
                    setCopied(true);
                  }}
                >
                  <Copy className="size-4" /> {copied ? "Copied" : "Copy"}
                </Button>
              </div>
              <p className="text-muted text-xs">
                Google Calendar: Other calendars → From URL. Outlook: Add calendar → Subscribe from
                web. Apple Calendar: File → New Calendar Subscription.
              </p>
            </div>
          )}
          {feed.data?.active && !url && (
            <p className="text-muted text-sm">
              Active since {formatDateTime(feed.data.created_at!)}
              {feed.data.last_accessed_at
                ? `, last read by your calendar ${formatDateTime(feed.data.last_accessed_at)}`
                : ", not read by a calendar yet"}
              .
            </p>
          )}
          <div className="flex flex-wrap gap-2">
            <Button
              onClick={() =>
                create.mutate(undefined, {
                  onSuccess: (res) => {
                    setUrl((res as Schemas["CalendarFeedOut"]).url ?? null);
                    setCopied(false);
                  },
                })
              }
              disabled={create.isPending}
            >
              <CalendarPlus className="size-4" />
              {feed.data?.active ? "Create a new link" : "Create calendar link"}
            </Button>
            {feed.data?.active && (
              <Button
                variant="danger"
                onClick={() => remove.mutate(undefined, { onSuccess: () => setUrl(null) })}
              >
                Turn off
              </Button>
            )}
          </div>
          {feed.data?.active && (
            <p className="text-muted text-xs">Creating a new link stops the old one working.</p>
          )}
          <ErrorText>{errorMessage(create.error || remove.error)}</ErrorText>
        </div>
      )}
    </Card>
  );
}

function ReminderSchedule({ orgId, isAdmin }: { orgId: string; isAdmin: boolean }) {
  const settings = useReminderSettings(orgId);
  const update = useUpdateReminderSettings(orgId);
  const [draft, setDraft] = useState<Record<string, string> | null>(null);
  const [saved, setSaved] = useState(false);
  const current = settings.data?.reminder_days;
  const values =
    draft ?? Object.fromEntries(Object.entries(current ?? {}).map(([k, v]) => [k, v.join(", ")]));

  return (
    <Card
      title="Reminder schedule"
      description="Days before each kind of deadline that the contract owner is reminded (0 = on the day). Applies to everyone in this organization."
    >
      {settings.isPending ? (
        <Loading />
      ) : (
        <form
          className="grid gap-4 sm:grid-cols-2"
          onSubmit={(e) => {
            e.preventDefault();
            const parsed: Record<string, number[]> = {};
            for (const [kind, text] of Object.entries(values)) {
              parsed[kind] = text
                .split(/[,\s]+/)
                .filter(Boolean)
                .map(Number)
                .filter((n) => Number.isInteger(n) && n >= 0);
            }
            update.mutate(
              { reminder_days: parsed },
              {
                onSuccess: () => {
                  setDraft(null);
                  setSaved(true);
                },
              },
            );
          }}
        >
          {Object.keys(values).map((kind) => (
            <Field key={kind} label={DEADLINE_KIND_LABELS[kind as Schemas["DeadlineKind"]] ?? kind}>
              <Input
                disabled={!isAdmin}
                value={values[kind]}
                onChange={(e) => {
                  setSaved(false);
                  setDraft({ ...values, [kind]: e.target.value });
                }}
              />
            </Field>
          ))}
          {isAdmin ? (
            <div className="flex items-center gap-3 sm:col-span-2">
              <Button type="submit" disabled={!draft || update.isPending}>
                Save schedule
              </Button>
              {saved && <span className="text-success text-sm">Saved</span>}
              <ErrorText>{errorMessage(update.error)}</ErrorText>
            </div>
          ) : (
            <p className="text-muted text-sm sm:col-span-2">Only admins can change the schedule.</p>
          )}
        </form>
      )}
    </Card>
  );
}

export default function SettingsPage() {
  const { orgId, isAdmin } = useCurrentOrg();
  return (
    <>
      <PageHeader title="Settings" description="Notifications, calendar and reminders." />
      <div className="grid gap-6 lg:grid-cols-2">
        <MyNotifications orgId={orgId} />
        <CalendarFeedCard orgId={orgId} />
        <div className="lg:col-span-2">
          <ReminderSchedule orgId={orgId} isAdmin={isAdmin} />
        </div>
      </div>
    </>
  );
}
