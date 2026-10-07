"use client";

import { Copy, Download, FileText, Sparkles, X } from "lucide-react";
import { useState } from "react";

import { formatIsoDate } from "@/components/app/contract-bits";
import { Button, ErrorText, Field, Input, Select } from "@/components/ui";
import { useDownload, useDraftNotice, type Schemas } from "@/lib/api";
import { NOTICE_KIND_LABELS } from "@/lib/labels";

type Kind = Schemas["NoticeKind"];

export function defaultNoticeKind(deadline?: Schemas["DeadlineOut"]): Kind {
  if (deadline?.kind === "option") return "option_exercise";
  if (deadline?.decision === "terminate") return "termination";
  if (deadline?.decision === "renegotiate") return "renegotiation";
  return "non_renewal";
}

export function NoticeDraftDialog({
  orgId,
  contract,
  deadline,
  onClose,
}: {
  orgId: string;
  contract: Schemas["ContractDetail"];
  deadline?: Schemas["DeadlineOut"];
  onClose: () => void;
}) {
  const draft = useDraftNotice(orgId, contract.id);
  const download = useDownload(orgId);
  const [kind, setKind] = useState<Kind>(defaultNoticeKind(deadline));
  const [sender, setSender] = useState("");
  const [instructions, setInstructions] = useState("");
  const [text, setText] = useState("");
  const [citations, setCitations] = useState<Schemas["Citation"][]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const run = async () => {
    setBusy(true);
    setError(null);
    setText("");
    setCitations([]);
    await draft(
      {
        kind,
        deadline_id: deadline?.id ?? null,
        sender: sender || null,
        instructions: instructions || null,
      },
      (e) => {
        if (e.type === "delta") setText((t) => t + e.text);
        else if (e.type === "done") {
          setText(e.text);
          setCitations(e.citations);
        } else setError(e.detail);
      },
    );
    setBusy(false);
  };

  const title = `${NOTICE_KIND_LABELS[kind]} - ${contract.title}`;

  return (
    <div
      className="fixed inset-0 z-30 flex items-start justify-center overflow-y-auto bg-black/40 p-4 md:p-10"
      role="dialog"
      aria-modal="true"
      aria-label="Draft a notice"
    >
      <div className="border-border bg-surface w-full max-w-3xl rounded-lg border shadow-xl">
        <header className="border-border flex items-center justify-between border-b px-5 py-4">
          <div>
            <h2 className="font-semibold">Draft a notice</h2>
            <p className="text-muted text-sm">
              {contract.title}
              {deadline && ` · ${deadline.label} by ${formatIsoDate(deadline.due_date)}`}
            </p>
          </div>
          <button
            onClick={onClose}
            aria-label="Close"
            className="text-muted hover:text-foreground rounded p-1"
          >
            <X className="size-5" />
          </button>
        </header>

        <div className="space-y-4 p-5">
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Type of notice">
              <Select value={kind} onChange={(e) => setKind(e.target.value as Kind)}>
                {Object.entries(NOTICE_KIND_LABELS).map(([v, l]) => (
                  <option key={v} value={v}>
                    {l}
                  </option>
                ))}
              </Select>
            </Field>
            <Field
              label="Sent by (optional)"
              hint="Your company and signatory, as it should appear"
            >
              <Input
                value={sender}
                placeholder="e.g. Client A Ltd, by its General Counsel"
                onChange={(e) => setSender(e.target.value)}
              />
            </Field>
            <Field label="Extra instructions (optional)" className="sm:col-span-2">
              <Input
                value={instructions}
                placeholder="e.g. Mention that we are open to a shorter renewal term"
                onChange={(e) => setInstructions(e.target.value)}
              />
            </Field>
          </div>
          <Button onClick={() => void run()} disabled={busy}>
            <Sparkles className="size-4" /> {text ? "Draft again" : "Draft with AI"}
          </Button>
          <ErrorText>{error}</ErrorText>

          {(text || busy) && (
            <>
              <textarea
                aria-label="Draft letter"
                className="border-border bg-background focus:ring-primary/40 min-h-80 w-full rounded-md border p-4 font-serif text-sm leading-relaxed outline-none focus:ring-2"
                value={text || "Drafting…"}
                readOnly={busy}
                onChange={(e) => setText(e.target.value)}
              />
              {citations.length > 0 && (
                <p className="text-muted text-xs">
                  Based on:{" "}
                  {Array.from(new Set(citations.flatMap((c) => c.clause_refs))).join(", ")}
                </p>
              )}
              <div className="border-warning/30 bg-warning/5 rounded-md border p-3 text-sm">
                <p className="font-medium">Before sending</p>
                <ul className="text-muted mt-1 list-disc space-y-0.5 pl-5">
                  <li>
                    Check the letter against the contract, and fill in anything in [brackets].
                  </li>
                  <li>
                    Send it by the method and to the address the notice clause requires
                    {contract.notice_details ? ` (${contract.notice_details})` : ""}.
                  </li>
                  {deadline && (
                    <li>
                      It must be sent by {formatIsoDate(deadline.due_date)}; this date already
                      allows for any deemed-receipt period.
                    </li>
                  )}
                  <li>Make sure the signatory is authorised to give notice.</li>
                </ul>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button
                  disabled={busy || !text}
                  onClick={() =>
                    download.mutate({
                      path: "/render-docx",
                      filename: `${title.replace(/[^\w\- ]/g, "").slice(0, 80)}.docx`,
                      body: { title, text },
                    })
                  }
                >
                  <Download className="size-4" /> Download Word
                </Button>
                <Button
                  variant="secondary"
                  disabled={busy || !text}
                  onClick={async () => {
                    await navigator.clipboard.writeText(text);
                    setCopied(true);
                  }}
                >
                  <Copy className="size-4" /> {copied ? "Copied" : "Copy text"}
                </Button>
              </div>
              <ErrorText>{download.error ? "Download failed" : null}</ErrorText>
            </>
          )}
          {!text && !busy && (
            <p className="text-muted flex items-center gap-2 text-sm">
              <FileText className="size-4" /> The draft uses the contract&apos;s own notice clause,
              term and deadline. Nothing is sent: you review, edit and download it.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
