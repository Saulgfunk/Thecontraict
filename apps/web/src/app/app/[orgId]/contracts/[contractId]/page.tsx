"use client";

import { RefreshCw, Trash2 } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";

import { AmendmentsCard } from "@/components/app/amendments";
import { ChatPanel } from "@/components/app/chat-panel";
import { ClauseViewer } from "@/components/app/clause-viewer";
import { ContractOverview } from "@/components/app/contract-overview";
import { Avatar } from "@/components/app/logo";
import { OwnerSelect } from "@/components/app/owner-select";
import { DateRulesCard, DeadlinesCard, PaymentTermsCard } from "@/components/app/contract-review";
import { ContractTerms } from "@/components/app/contract-terms";
import { useCurrentOrg } from "@/components/app/use-org";
import { Badge, Button, Card, ErrorText, Loading, PageHeader } from "@/components/ui";
import {
  useAiEnabled,
  useContract,
  useDeleteContract,
  useReprocessContract,
  useWorkspace,
} from "@/lib/api";
import { CONTRACT_STATUS } from "@/lib/labels";
import { cn, errorMessage } from "@/lib/utils";

type Section = "dates" | "terms" | "changes";

export default function ContractPage() {
  const { contractId } = useParams<{ contractId: string }>();
  const { orgId } = useCurrentOrg();
  const router = useRouter();
  const contract = useContract(orgId, contractId);
  const workspace = useWorkspace(orgId, contract.data?.workspace_id ?? "");
  const reprocess = useReprocessContract(orgId, contractId);
  const remove = useDeleteContract(orgId, contractId);
  const aiEnabled = useAiEnabled();
  // Links from workspace chat answers carry the cited clauses in the URL hash (#C5,C8).
  // (The clause list only renders after data loads, so reading window here is safe.)
  const [selected, setSelected] = useState<string[]>(() =>
    typeof window === "undefined"
      ? []
      : window.location.hash
          .slice(1)
          .split(",")
          .filter((r) => /^C\d+$/.test(r)),
  );
  const [tab, setTab] = useState<"document" | "chat">("document");
  const [section, setSection] = useState<Section | null>(null);
  const showRefs = (refs: string[]) => {
    setSelected(refs);
    setTab("document");
  };

  if (contract.isPending) return <Loading />;
  if (contract.error) return <ErrorText>{errorMessage(contract.error)}</ErrorText>;
  const c = contract.data;
  const role = workspace.data?.my_role;
  const canEdit = role === "admin" || role === "editor";
  const doc = c.documents.at(-1);
  const busy = doc && (doc.status === "uploaded" || doc.status === "processing");
  const status = CONTRACT_STATUS[c.status];
  const amendments = c.amendments?.length ?? 0;
  const sections: [Section, string][] = [
    ["dates", "All dates"],
    ["terms", (c.pending_review ?? 0) > 0 ? `Terms (${c.pending_review} to check)` : "Terms"],
    ["changes", amendments ? `Amendments (${amendments})` : "Amendments"],
  ];
  // Open on the terms when they still need entering or checking.
  const current: Section =
    section ?? ((c.pending_review ?? 0) > 0 || !c.reviewed_at ? "terms" : "dates");

  return (
    <>
      <Link href={`/app/${orgId}/contracts`} className="text-muted text-sm hover:underline">
        ← Contracts
      </Link>
      <PageHeader
        title={c.title}
        eyebrow={workspace.data?.name}
        leading={<Avatar name={c.counterparty_name ?? c.title} className="size-14 text-lg" />}
        description={[c.counterparty_name, c.contract_type].filter(Boolean).join(" · ")}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            {c.status !== "active" && <Badge tone={status.tone}>{status.label}</Badge>}
            <OwnerSelect orgId={orgId} contract={c} canEdit={canEdit} />
            {canEdit && (
              <>
                {aiEnabled && doc && (
                  <Button
                    variant="secondary"
                    disabled={busy || reprocess.isPending}
                    onClick={() => reprocess.mutate()}
                    title="Analyse the document again. Values you reviewed are kept."
                  >
                    <RefreshCw className="size-4" /> Re-analyse
                  </Button>
                )}
                <Button
                  variant="ghost"
                  aria-label="Delete contract"
                  title="Delete contract"
                  disabled={remove.isPending}
                  onClick={() => {
                    if (window.confirm(`Delete "${c.title}" and its document?`)) {
                      remove.mutate(undefined, {
                        onSuccess: () => router.replace(`/app/${orgId}/contracts`),
                      });
                    }
                  }}
                >
                  <Trash2 className="size-4" />
                </Button>
              </>
            )}
          </div>
        }
      />
      <ErrorText>{errorMessage(reprocess.error || remove.error)}</ErrorText>

      {busy && (
        <div className="border-primary/30 bg-primary/5 mb-6 rounded-lg border p-4 text-sm">
          <p className="font-medium">Analysing the contract…</p>
          <p className="text-muted">
            Reading the document and finding dates, notice periods and payment terms. This usually
            takes under a minute; the page updates automatically.
          </p>
        </div>
      )}
      {doc?.ai_status === "skipped" && !c.reviewed_at && (
        <div className="border-primary/30 bg-primary/5 mb-6 rounded-lg border p-4 text-sm">
          <p className="font-medium">Enter the key terms</p>
          <p className="text-muted">
            AI analysis is switched off, so the dates were not read automatically.{" "}
            {doc.text_source === "needs_ocr"
              ? "This is a scanned document: open the original to read it."
              : "The document is shown on the right for reference."}{" "}
            Open the &ldquo;Terms&rdquo; tab below to fill in the term, renewal and notice period,
            then confirm.
          </p>
        </div>
      )}
      {doc?.status === "failed" && (
        <div className="border-danger/30 bg-danger/5 mb-6 rounded-lg border p-4 text-sm">
          <p className="text-danger font-medium">The analysis failed</p>
          <p>{doc.error}</p>
          <p className="text-muted mt-1">
            You can try again with Re-analyse, or enter the key terms by hand below.
          </p>
        </div>
      )}

      <div className="grid gap-6 xl:grid-cols-5">
        <div className="space-y-6 xl:col-span-3">
          <ContractOverview
            orgId={orgId}
            contract={c}
            canEdit={canEdit}
            onReview={() => setSection("terms")}
          />
          <div>
            <div className="border-border mb-4 flex gap-1 border-b" role="tablist">
              {sections.map(([key, label]) => (
                <button
                  key={key}
                  role="tab"
                  aria-selected={current === key}
                  onClick={() => setSection(key)}
                  className={cn(
                    "-mb-px border-b-2 px-3 py-2 text-sm",
                    current === key
                      ? "border-primary text-primary font-medium"
                      : "text-muted hover:text-foreground border-transparent",
                  )}
                >
                  {label}
                </button>
              ))}
            </div>
            {current === "dates" && <DeadlinesCard orgId={orgId} contract={c} canEdit={canEdit} />}
            {current === "terms" && (
              <div className="space-y-6">
                <ContractTerms
                  key={c.id}
                  orgId={orgId}
                  contract={c}
                  canEdit={canEdit}
                  onSelectRefs={showRefs}
                />
                <DateRulesCard
                  orgId={orgId}
                  contract={c}
                  canEdit={canEdit}
                  onSelectRefs={showRefs}
                />
                <PaymentTermsCard
                  orgId={orgId}
                  contract={c}
                  canEdit={canEdit}
                  onSelectRefs={showRefs}
                />
              </div>
            )}
            {current === "changes" && (
              <AmendmentsCard orgId={orgId} contract={c} canEdit={canEdit} />
            )}
          </div>
        </div>
        <div className="xl:col-span-2">
          <div className="xl:sticky xl:top-6 xl:h-[calc(100vh-3rem)]">
            <Card
              className="flex h-full flex-col [&>div]:min-h-0 [&>div]:flex-1"
              title={tab === "document" ? "Document" : "Ask about this contract"}
              actions={
                aiEnabled && doc ? (
                  <div className="border-border flex rounded-md border p-0.5 text-sm">
                    {(["document", "chat"] as const).map((t) => (
                      <button
                        key={t}
                        onClick={() => setTab(t)}
                        className={cn(
                          "rounded px-3 py-1",
                          tab === t ? "bg-primary text-primary-foreground" : "text-muted",
                        )}
                      >
                        {t === "document" ? "Document" : "Ask AI"}
                      </button>
                    ))}
                  </div>
                ) : null
              }
            >
              {tab === "document" || !aiEnabled ? (
                <ClauseViewer
                  orgId={orgId}
                  contractId={c.id}
                  document={doc}
                  selected={selected}
                  canEdit={canEdit}
                />
              ) : (
                <ChatPanel
                  className="h-full"
                  orgId={orgId}
                  workspaceId={c.workspace_id}
                  contractId={c.id}
                  onCitation={(cit) => showRefs(cit.clause_refs)}
                />
              )}
            </Card>
          </div>
        </div>
      </div>
    </>
  );
}
