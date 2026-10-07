"use client";

import { ExternalLink } from "lucide-react";
import { useEffect, useRef } from "react";

import { Button, ErrorText, Loading } from "@/components/ui";
import { useClauses, useOpenDocument, type Schemas } from "@/lib/api";
import { cn, errorMessage } from "@/lib/utils";

export function ClauseViewer({
  orgId,
  document,
  selected,
}: {
  orgId: string;
  document: Schemas["DocumentOut"] | undefined;
  selected: string[];
}) {
  const clauses = useClauses(orgId, document?.id, document?.status);
  const open = useOpenDocument(orgId);
  const container = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!selected.length || !container.current) return;
    const el = container.current.querySelector<HTMLElement>(`[data-ref="${selected[0]}"]`);
    el?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [selected, clauses.data]);

  if (!document) return <p className="text-muted text-sm">No document.</p>;

  return (
    <div className="flex h-full flex-col">
      <div className="mb-3 flex items-center justify-between gap-2">
        <div className="min-w-0 text-sm">
          <p className="truncate font-medium" title={document.filename}>
            {document.filename}
          </p>
          <p className="text-muted text-xs">
            {[
              document.page_count ? `${document.page_count} pages` : null,
              document.text_source === "ocr" ? "scanned (text recognised by AI)" : null,
            ]
              .filter(Boolean)
              .join(" · ")}
          </p>
        </div>
        <Button
          variant="secondary"
          className="h-8 shrink-0 px-3"
          onClick={() => open.mutate(document.id)}
        >
          <ExternalLink className="size-3.5" /> Original
        </Button>
      </div>
      <ErrorText>{errorMessage(open.error)}</ErrorText>
      <div
        ref={container}
        className="border-border bg-background min-h-0 flex-1 space-y-3 overflow-y-auto rounded-md border p-3"
      >
        {document.status !== "ready" ? (
          <Loading label={document.status === "failed" ? "Not available" : "Reading document…"} />
        ) : clauses.isPending ? (
          <Loading />
        ) : clauses.error ? (
          <ErrorText>{errorMessage(clauses.error)}</ErrorText>
        ) : (
          clauses.data.map((c) => (
            <section
              key={c.id}
              data-ref={c.ref}
              className={cn(
                "scroll-mt-2 rounded-md p-2 text-sm transition-colors",
                selected.includes(c.ref) && "bg-warning/15 ring-warning/40 ring-1",
              )}
            >
              <header className="text-muted mb-1 flex items-baseline gap-2 text-xs">
                <span className="font-mono">{c.ref}</span>
                {c.page_start && (
                  <span>
                    p. {c.page_start}
                    {c.page_end && c.page_end !== c.page_start ? `–${c.page_end}` : ""}
                  </span>
                )}
              </header>
              {/* Without a heading, the number is already the start of the text. */}
              {c.heading && (
                <p className="font-semibold">{[c.number, c.heading].filter(Boolean).join(" ")}</p>
              )}
              <p className="whitespace-pre-line">{c.text}</p>
            </section>
          ))
        )}
      </div>
    </div>
  );
}
