"use client";

import { FileText, Upload } from "lucide-react";
import Link from "next/link";
import { useRef, useState } from "react";

import { DueText, deadlineSentence } from "@/components/app/deadline-actions";
import { Badge, ErrorText, Loading } from "@/components/ui";
import { useAiEnabled, useAllContracts, useUploadContract } from "@/lib/api";
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
          "border-border text-muted hover:border-primary/50 flex w-full flex-col items-center gap-2 rounded-lg border-2 border-dashed px-4 py-6 text-sm transition",
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

export function ContractsPanel({
  orgId,
  workspaceId,
  canEdit,
  search = "",
}: {
  orgId: string;
  /** Omit to list contracts from every workspace the user can access. */
  workspaceId?: string;
  canEdit: boolean;
  search?: string;
}) {
  const contracts = useAllContracts(orgId, workspaceId);
  const needle = search.trim().toLowerCase();
  const list = contracts.data?.filter(
    (c) =>
      !needle ||
      [c.title, c.counterparty_name, c.contract_type, c.workspace_name].some((v) =>
        v?.toLowerCase().includes(needle),
      ),
  );

  return (
    <>
      {canEdit && workspaceId && <Uploader orgId={orgId} workspaceId={workspaceId} />}
      {contracts.isPending ? (
        <Loading />
      ) : contracts.error ? (
        <ErrorText>{errorMessage(contracts.error)}</ErrorText>
      ) : !list?.length ? (
        <p className="text-muted text-sm">
          {needle ? "No contracts match your search." : "No contracts yet."}
        </p>
      ) : (
        <ul className="divide-border divide-y">
          {list.map((c) => {
            const doc = c.documents.at(-1);
            const busy = doc && (doc.status === "uploaded" || doc.status === "processing");
            const status = CONTRACT_STATUS[c.status];
            const next = c.next_deadline;
            return (
              <li key={c.id}>
                <Link
                  href={`/app/${orgId}/contracts/${c.id}`}
                  className="group flex flex-col gap-2 py-3 sm:flex-row sm:items-center sm:justify-between sm:gap-4"
                >
                  <span className="flex min-w-0 flex-1 items-center gap-3">
                    <FileText className="text-muted size-4 shrink-0" />
                    <span className="min-w-0">
                      <span className="group-hover:text-primary block font-medium">{c.title}</span>
                      <span className="text-muted block truncate text-xs">
                        {[c.counterparty_name, workspaceId ? null : c.workspace_name]
                          .filter(Boolean)
                          .join(" · ")}
                      </span>
                    </span>
                  </span>
                  <span className="flex flex-wrap items-center gap-x-3 gap-y-1 pl-7 sm:w-80 sm:shrink-0 sm:justify-end sm:pl-0 sm:text-right">
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
                      <span className="text-xs">
                        <span className="block">
                          {deadlineSentence({ ...next, counterparty_name: c.counterparty_name })}
                        </span>
                        <DueText date={next.due_date} className="text-xs" />
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
