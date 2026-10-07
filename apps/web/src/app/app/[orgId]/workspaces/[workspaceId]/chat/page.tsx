"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";

import { ChatPanel } from "@/components/app/chat-panel";
import { useCurrentOrg } from "@/components/app/use-org";
import { Card, PageHeader } from "@/components/ui";
import { useWorkspace } from "@/lib/api";

export default function WorkspaceChatPage() {
  const { workspaceId } = useParams<{ workspaceId: string }>();
  const { orgId } = useCurrentOrg();
  const router = useRouter();
  const workspace = useWorkspace(orgId, workspaceId);

  return (
    <>
      <Link
        href={`/app/${orgId}/workspaces/${workspaceId}`}
        className="text-muted text-sm hover:underline"
      >
        ← {workspace.data?.name ?? "Workspace"}
      </Link>
      <PageHeader
        title="Ask AI"
        description="Questions across every contract in this workspace. Click a source to open the clause."
      />
      <Card className="flex h-[calc(100vh-14rem)] min-h-[28rem] flex-col [&>div]:min-h-0 [&>div]:flex-1">
        <ChatPanel
          className="h-full"
          orgId={orgId}
          workspaceId={workspaceId}
          onCitation={(c) =>
            router.push(`/app/${orgId}/contracts/${c.contract_id}#${c.clause_refs.join(",")}`)
          }
        />
      </Card>
    </>
  );
}
