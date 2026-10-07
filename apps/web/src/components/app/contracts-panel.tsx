"use client";

import { Upload } from "lucide-react";
import Link from "next/link";
import { useRef, useState } from "react";

import { DateTile, DueText, deadlineSentence } from "@/components/app/deadline-actions";
import { Avatar } from "@/components/app/logo";
import { Badge, ErrorText, Loading } from "@/components/ui";
import { useAiEnabled, useAllContracts, useUploadContract, type Schemas } from "@/lib/api";
import { CONTRACT_STATUS } from "@/lib/labels";
import { cn, errorMessage } from "@/lib/utils";

const ACCEPT =
  ".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document";

function Uploader({ orgId, workspaceId }: { orgId: string; workspaceId: string }) {
  const upload = useUploadContract(orgId, workspaceId);
  const aiEnabled = useAiEnabled();
  const input = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);

  const send = async (files: FileList | null) => {
    if (!files?.length) return;
    const failed: string[] = [];
    for (const file of Array.from(files)) {
      try {
        await upload.mutateAsync(file);
      } catch (e) {
        failed.push(`${file.name}: ${errorMessage(e)}`);
      }
    }
    setErrors(failed);
  };

  return (
    <div className="mb-5">
      <button
        type="button"
        onClick={() => input.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          void send(e.dataTransfer.files);
        }}
        className={cn(
          "border-border bg-surface-2 text-muted hover:border-primary/50 hover:bg-primary/[0.03] flex w-full flex-col items-center gap-2 rounded-2xl border-2 border-dashed px-4 py-7 text-sm transition",
          dragging && "border-primary bg-primary/5",
        )}
      >
        <Upload className="size-5" />
        {upload.isPending ? (
          <span>Uploading…</span>
        ) : (
          <span>
            <span className="text-primary font-medium">Upload contracts</span> or drag them here
            (PDF or Word{aiEnabled ? ", scanned PDFs too" : ""})
            {aiEnabled === false && (
              <span className="mt-1 block text-xs">
                AI analysis is off: after uploading, you enter the key terms yourself. Or use
                &ldquo;New contract&rdquo; to type them in first.
              </span>
            )}
          </span>
        )}
      </button>
      <input
        ref={input}
        type="file"
        accept={ACCEPT}
        multiple
        hidden
        onChange={(e) => {
          void send(e.target.files);
          e.target.value = "";
        }}
      />
      {errors.map((e) => (
        <ErrorText key={e}>{e}</ErrorText>
      ))}
    </div>
  );
}

type Item = Schemas["ContractListItem"];
type Filter = "all" | "check" | "no_copy" | "no_dates";

const FILTERS: Record<Filter, { label: string; test: (c: Item) => boolean }> = {
  all: { label: "All", test: () => true },
  check: { label: "To check", test: (c) => (c.pending_review ?? 0) > 0 },
  no_copy: { label: "No signed copy", test: (c) => c.documents.length === 0 },
  no_dates: { label: "No upcoming dates", test: (c) => !c.next_deadline },
};

export function ContractsPanel({
  orgId,
  workspaceId,
  canEdit,
  search = "",
  filters = false,
}: {
  orgId: string;
  /** Omit to list contracts from every workspace the user can access. */
  workspaceId?: string;
  canEdit: boolean;
  search?: string;
  /** Show the quick filters (to check, no signed copy, no upcoming dates). */
  filters?: boolean;
}) {
  const contracts = useAllContracts(orgId, workspaceId);
  const [show, setShow] = useState<Filter>("all");
  const needle = search.trim().toLowerCase();
  const matching = contracts.data?.filter(
    (c) =>
      !needle ||
      [c.title, c.counterparty_name, c.contract_type, c.workspace_name].some((v) =>
        v?.toLowerCase().includes(needle),
      ),
  );
  const list = matching?.filter(FILTERS[show].test);

  return (
    <>
      {canEdit && workspaceId && <Uploader orgId={orgId} workspaceId={workspaceId} />}
      {filters && matching && matching.length > 0 && (
        <div className="mb-4 flex flex-wrap gap-1.5" role="group" aria-label="Show">
          {(Object.keys(FILTERS) as Filter[]).map((key) => {
            const count = matching.filter(FILTERS[key].test).length;
            if (key !== "all" && count === 0 && show !== key) return null;
            return (
              <button
                key={key}
                aria-pressed={show === key}
                onClick={() => setShow(key)}
                className={cn(
                  "rounded-full px-3 py-1 text-xs font-medium ring-1 transition-colors ring-inset",
                  show === key
                    ? "bg-primary text-primary-foreground ring-primary"
                    : "text-muted ring-border hover:text-foreground bg-surface",
                )}
              >
                {FILTERS[key].label}
                <span className="ml-1.5 opacity-70">{count}</span>
              </button>
            );
          })}
        </div>
      )}
      {contracts.isPending ? (
        <Loading />
      ) : contracts.error ? (
        <ErrorText>{errorMessage(contracts.error)}</ErrorText>
      ) : !list?.length ? (
        <p className="text-muted text-sm">
          {needle ? "No contracts match your search." : "No contracts yet."}
        </p>
      ) : (
        <ul className="space-y-0.5">
          {list.map((c) => {
            const doc = c.documents.at(-1);
            const busy = doc && (doc.status === "uploaded" || doc.status === "processing");
            const status = CONTRACT_STATUS[c.status];
            const next = c.next_deadline;
            return (
              <li key={c.id}>
                <Link
                  href={`/app/${orgId}/contracts/${c.id}`}
                  className="group hover:bg-foreground/[0.025] -mx-3 flex flex-col gap-3 rounded-xl px-3 py-3 transition-colors sm:flex-row sm:items-center sm:justify-between sm:gap-4"
                >
                  <span className="flex min-w-0 flex-1 items-center gap-3.5">
                    <Avatar name={c.counterparty_name ?? c.title} />
                    <span className="min-w-0">
                      <span className="group-hover:text-primary block font-medium">{c.title}</span>
                      <span className="text-muted block truncate text-xs">
                        {[c.counterparty_name, workspaceId ? null : c.workspace_name]
                          .filter(Boolean)
                          .join(" · ")}
                      </span>
                    </span>
                  </span>
                  <span className="flex flex-wrap items-center gap-x-3 gap-y-1 pl-[3.375rem] sm:w-80 sm:shrink-0 sm:justify-end sm:pl-0 sm:text-right">
                    {busy ? (
                      <Badge tone="primary">Reading the document…</Badge>
                    ) : doc?.status === "failed" ? (
                      <Badge tone="danger">Could not read the document</Badge>
                    ) : (c.pending_review ?? 0) > 0 ? (
                      <Badge tone="warning">
                        Check {c.pending_review} item{c.pending_review === 1 ? "" : "s"}
                      </Badge>
                    ) : c.status !== "active" ? (
                      <Badge tone={status.tone}>{status.label}</Badge>
                    ) : null}
                    {next ? (
                      <span className="flex items-center gap-3 sm:flex-row-reverse">
                        <DateTile date={next.due_date} className="size-10 rounded-lg" />
                        <span className="text-xs">
                          <span className="block font-medium">
                            {deadlineSentence({ ...next, counterparty_name: c.counterparty_name })}
                          </span>
                          <DueText date={next.due_date} className="text-xs" />
                        </span>
                      </span>
                    ) : (
                      !busy && <span className="text-muted text-xs">No upcoming dates</span>
                    )}
                  </span>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </>
  );
}
