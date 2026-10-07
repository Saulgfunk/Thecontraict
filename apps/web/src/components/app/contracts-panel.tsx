"use client";

import { FileText, Upload } from "lucide-react";
import Link from "next/link";
import { useRef, useState } from "react";

import { Countdown, formatIsoDate } from "@/components/app/contract-bits";
import { Badge, ErrorText, Loading } from "@/components/ui";
import { useContracts, useUploadContract } from "@/lib/api";
import { CONTRACT_STATUS } from "@/lib/labels";
import { cn, errorMessage } from "@/lib/utils";

const ACCEPT =
  ".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document";

function Uploader({ orgId, workspaceId }: { orgId: string; workspaceId: string }) {
  const upload = useUploadContract(orgId, workspaceId);
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
            (PDF or Word, scanned PDFs too)
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
}: {
  orgId: string;
  workspaceId: string;
  canEdit: boolean;
}) {
  const contracts = useContracts(orgId, workspaceId);

  return (
    <>
      {canEdit && <Uploader orgId={orgId} workspaceId={workspaceId} />}
      {contracts.isPending ? (
        <Loading />
      ) : contracts.error ? (
        <ErrorText>{errorMessage(contracts.error)}</ErrorText>
      ) : contracts.data.length === 0 ? (
        <p className="text-muted text-sm">No contracts yet.</p>
      ) : (
        <ul className="divide-border divide-y">
          {contracts.data.map((c) => {
            const doc = c.documents.at(-1);
            const busy = doc && (doc.status === "uploaded" || doc.status === "processing");
            const status = CONTRACT_STATUS[c.status];
            return (
              <li key={c.id}>
                <Link
                  href={`/app/${orgId}/contracts/${c.id}`}
                  className="hover:text-primary flex flex-wrap items-center justify-between gap-3 py-3"
                >
                  <span className="flex min-w-0 items-center gap-3">
                    <FileText className="text-muted size-4 shrink-0" />
                    <span className="min-w-0">
                      <span className="block truncate font-medium">{c.title}</span>
                      <span className="text-muted block truncate text-xs">
                        {[c.counterparty_name, c.contract_type, doc?.filename]
                          .filter(Boolean)
                          .join(" · ")}
                      </span>
                    </span>
                  </span>
                  <span className="flex flex-wrap items-center gap-2">
                    {busy ? (
                      <Badge tone="primary">Analysing…</Badge>
                    ) : doc?.status === "failed" ? (
                      <Badge tone="danger">Analysis failed</Badge>
                    ) : (
                      <>
                        {(c.pending_review ?? 0) > 0 && (
                          <Badge tone="warning">{c.pending_review} to review</Badge>
                        )}
                        <Badge tone={status.tone}>{status.label}</Badge>
                      </>
                    )}
                    {c.next_deadline && (
                      <span className="text-muted flex items-center gap-2 text-xs">
                        {c.next_deadline.label}: {formatIsoDate(c.next_deadline.due_date)}
                        <Countdown date={c.next_deadline.due_date} />
                      </span>
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
