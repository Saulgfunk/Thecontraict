"use client";

import {
  ApiError,
  createApiClient,
  unwrap,
  type ApiClient,
  type Schemas,
} from "@contraict/api-client";
import {
  QueryClient,
  QueryClientProvider,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { createContext, useContext, useEffect, useMemo, useRef, useState } from "react";

import { useAuthState } from "./auth";
import { API_URL } from "./config";

export type { Schemas };

const ApiContext = createContext<ApiClient | null>(null);

function useApi(): ApiClient {
  const api = useContext(ApiContext);
  if (!api) throw new Error("useApi must be used inside <ApiProvider>");
  return api;
}

export function ApiProvider({ children }: { children: React.ReactNode }) {
  const auth = useAuthState();
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: { queries: { staleTime: 30_000, retry: 1 } },
      }),
  );
  const api = useMemo(
    () => createApiClient({ baseUrl: API_URL, getHeaders: auth.getHeaders }),
    [auth.getHeaders],
  );
  // Never show one user's cached data to another after switching accounts. Only clear on
  // an actual change of user: clearing when auth first resolves would drop in-flight queries.
  const userKey = auth.status === "signed-in" ? auth.email : null;
  const lastUser = useRef<string | null>(null);
  useEffect(() => {
    if (auth.status === "loading") return;
    if (lastUser.current !== null && lastUser.current !== userKey) queryClient.clear();
    lastUser.current = userKey;
  }, [auth.status, userKey, queryClient]);
  return (
    <ApiContext.Provider value={api}>
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    </ApiContext.Provider>
  );
}

// ---- Queries ----

export function useMe(enabled = true) {
  const api = useApi();
  return useQuery({
    queryKey: ["me"],
    queryFn: () => unwrap(api.GET("/me")),
    enabled,
  });
}

export function useOrganization(orgId: string) {
  const api = useApi();
  return useQuery({
    queryKey: ["org", orgId],
    queryFn: () =>
      unwrap(api.GET("/organizations/{org_id}", { params: { path: { org_id: orgId } } })),
  });
}

export function useOrgMembers(orgId: string) {
  const api = useApi();
  return useQuery({
    queryKey: ["org", orgId, "members"],
    queryFn: () =>
      unwrap(api.GET("/organizations/{org_id}/members", { params: { path: { org_id: orgId } } })),
  });
}

export function useWorkspaces(orgId: string) {
  const api = useApi();
  return useQuery({
    queryKey: ["org", orgId, "workspaces"],
    queryFn: () =>
      unwrap(
        api.GET("/organizations/{org_id}/workspaces", { params: { path: { org_id: orgId } } }),
      ),
  });
}

export function useWorkspace(orgId: string, workspaceId: string) {
  const api = useApi();
  return useQuery({
    queryKey: ["org", orgId, "workspaces", workspaceId],
    enabled: !!workspaceId,
    queryFn: () =>
      unwrap(
        api.GET("/organizations/{org_id}/workspaces/{workspace_id}", {
          params: { path: { org_id: orgId, workspace_id: workspaceId } },
        }),
      ),
  });
}

export function useWorkspaceMembers(orgId: string, workspaceId: string) {
  const api = useApi();
  return useQuery({
    queryKey: ["org", orgId, "workspaces", workspaceId, "members"],
    queryFn: () =>
      unwrap(
        api.GET("/organizations/{org_id}/workspaces/{workspace_id}/members", {
          params: { path: { org_id: orgId, workspace_id: workspaceId } },
        }),
      ),
  });
}

export function useAuditEvents(orgId: string) {
  const api = useApi();
  return useQuery({
    queryKey: ["org", orgId, "audit"],
    queryFn: () =>
      unwrap(
        api.GET("/organizations/{org_id}/audit-events", {
          params: { path: { org_id: orgId }, query: { limit: 200 } },
        }),
      ),
  });
}

// ---- Mutations ----

export function useCreateOrganization() {
  const api = useApi();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Schemas["OrganizationCreate"]) =>
      unwrap(api.POST("/organizations", { body })),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["me"] }),
  });
}

export function useCreateWorkspace(orgId: string) {
  const api = useApi();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Schemas["WorkspaceCreate"]) =>
      unwrap(
        api.POST("/organizations/{org_id}/workspaces", {
          params: { path: { org_id: orgId } },
          body,
        }),
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["org", orgId] }),
  });
}

export function useAddOrgMember(orgId: string) {
  const api = useApi();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Schemas["OrgMemberCreate"]) =>
      unwrap(
        api.POST("/organizations/{org_id}/members", { params: { path: { org_id: orgId } }, body }),
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["org", orgId] }),
  });
}

export function useUpdateOrgMember(orgId: string) {
  const api = useApi();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ memberId, role }: { memberId: string; role: Schemas["OrgRole"] }) =>
      unwrap(
        api.PATCH("/organizations/{org_id}/members/{member_id}", {
          params: { path: { org_id: orgId, member_id: memberId } },
          body: { role },
        }),
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["org", orgId] }),
  });
}

export function useRemoveOrgMember(orgId: string) {
  const api = useApi();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (memberId: string) =>
      unwrap(
        api.DELETE("/organizations/{org_id}/members/{member_id}", {
          params: { path: { org_id: orgId, member_id: memberId } },
        }),
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["org", orgId] }),
  });
}

export function useSetWorkspaceMember(orgId: string, workspaceId: string) {
  const api = useApi();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Schemas["WorkspaceMemberCreate"]) =>
      unwrap(
        api.POST("/organizations/{org_id}/workspaces/{workspace_id}/members", {
          params: { path: { org_id: orgId, workspace_id: workspaceId } },
          body,
        }),
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["org", orgId] }),
  });
}

export function useRemoveWorkspaceMember(orgId: string, workspaceId: string) {
  const api = useApi();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (memberId: string) =>
      unwrap(
        api.DELETE("/organizations/{org_id}/workspaces/{workspace_id}/members/{member_id}", {
          params: { path: { org_id: orgId, workspace_id: workspaceId, member_id: memberId } },
        }),
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["org", orgId] }),
  });
}

export function useNoticePreview() {
  const api = useApi();
  return useMutation({
    mutationFn: (body: Schemas["NoticePreviewIn"]) =>
      unwrap(api.POST("/deadlines/notice-preview", { body })),
  });
}

// ---- Contracts ----

type ContractSummary = Schemas["ContractSummary"];
type ContractDetail = Schemas["ContractDetail"];

const isProcessing = (c: { documents: { status: string }[] }) =>
  c.documents.some((d) => d.status === "uploaded" || d.status === "processing");

/** Contracts across every workspace the user can access (optionally one workspace). */
export function useAllContracts(orgId: string, workspaceId?: string) {
  const api = useApi();
  return useQuery({
    queryKey: ["org", orgId, "contracts", workspaceId ?? "all"],
    queryFn: () =>
      unwrap(
        api.GET("/organizations/{org_id}/contracts", {
          params: {
            path: { org_id: orgId },
            query: workspaceId ? { workspace_id: workspaceId } : {},
          },
        }),
      ),
    refetchInterval: (q) =>
      (q.state.data as ContractSummary[] | undefined)?.some(isProcessing) ? 2500 : false,
  });
}

export function useContracts(orgId: string, workspaceId: string) {
  const api = useApi();
  return useQuery({
    queryKey: ["org", orgId, "workspaces", workspaceId, "contracts"],
    queryFn: () =>
      unwrap(
        api.GET("/organizations/{org_id}/workspaces/{workspace_id}/contracts", {
          params: { path: { org_id: orgId, workspace_id: workspaceId } },
        }),
      ),
    // Poll while documents are being analysed.
    refetchInterval: (q) =>
      (q.state.data as ContractSummary[] | undefined)?.some(isProcessing) ? 2500 : false,
  });
}

export function useContract(orgId: string, contractId: string) {
  const api = useApi();
  return useQuery({
    queryKey: ["org", orgId, "contracts", contractId],
    queryFn: () =>
      unwrap(
        api.GET("/organizations/{org_id}/contracts/{contract_id}", {
          params: { path: { org_id: orgId, contract_id: contractId } },
        }),
      ),
    refetchInterval: (q) => {
      const data = q.state.data as ContractDetail | undefined;
      return data && isProcessing(data) ? 2500 : false;
    },
  });
}

export function useClauses(orgId: string, documentId: string | undefined, status?: string) {
  const api = useApi();
  return useQuery({
    queryKey: ["org", orgId, "documents", documentId, "clauses", status],
    enabled: !!documentId,
    queryFn: () =>
      unwrap(
        api.GET("/organizations/{org_id}/documents/{document_id}/clauses", {
          params: { path: { org_id: orgId, document_id: documentId! } },
        }),
      ),
  });
}

export function useDeadlines(
  orgId: string,
  query: { workspace_id?: string; from?: string; to?: string; include_closed?: boolean } = {},
) {
  const api = useApi();
  return useQuery({
    queryKey: ["org", orgId, "deadlines", query],
    queryFn: () =>
      unwrap(
        api.GET("/organizations/{org_id}/deadlines", {
          params: { path: { org_id: orgId }, query },
        }),
      ),
  });
}

/** Multipart upload (not expressible through the generated JSON client). */
export function useUploadContract(orgId: string, workspaceId: string) {
  const auth = useAuthState();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (file: File): Promise<ContractSummary> => {
      const form = new FormData();
      form.append("file", file);
      const res = await fetch(
        `${API_URL}/organizations/${orgId}/workspaces/${workspaceId}/contracts`,
        { method: "POST", body: form, headers: await auth.getHeaders() },
      );
      const body = await res.json().catch(() => null);
      if (!res.ok) {
        const detail = body?.detail;
        throw new ApiError(res.status, typeof detail === "object" ? detail.message : detail);
      }
      return body as ContractSummary;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["org", orgId] }),
  });
}

/** Fetch the original file with auth headers and open it in a new tab. */
export function useOpenDocument(orgId: string) {
  const auth = useAuthState();
  return useMutation({
    mutationFn: async (documentId: string) => {
      // Open the tab synchronously so pop-up blockers allow it.
      const tab = window.open("", "_blank");
      const res = await fetch(`${API_URL}/organizations/${orgId}/documents/${documentId}/file`, {
        headers: await auth.getHeaders(),
      });
      if (!res.ok) {
        tab?.close();
        throw new ApiError(res.status, "Could not open the document");
      }
      const url = URL.createObjectURL(await res.blob());
      if (tab) tab.location.href = url;
      else window.location.href = url;
      setTimeout(() => URL.revokeObjectURL(url), 60_000);
    },
  });
}

function useContractMutation<TVars>(
  orgId: string,
  fn: (api: ApiClient, vars: TVars) => Promise<unknown>,
) {
  const api = useApi();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: TVars) => fn(api, vars),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["org", orgId] }),
  });
}

export function useUpdateContract(orgId: string, contractId: string) {
  return useContractMutation(orgId, (api, body: Schemas["ContractUpdate"]) =>
    unwrap(
      api.PATCH("/organizations/{org_id}/contracts/{contract_id}", {
        params: { path: { org_id: orgId, contract_id: contractId } },
        body,
      }),
    ),
  );
}

export function useConfirmTerms(orgId: string, contractId: string) {
  return useContractMutation<void>(orgId, (api) =>
    unwrap(
      api.POST("/organizations/{org_id}/contracts/{contract_id}/confirm-terms", {
        params: { path: { org_id: orgId, contract_id: contractId } },
      }),
    ),
  );
}

export function useReprocessContract(orgId: string, contractId: string) {
  return useContractMutation<void>(orgId, (api) =>
    unwrap(
      api.POST("/organizations/{org_id}/contracts/{contract_id}/reprocess", {
        params: { path: { org_id: orgId, contract_id: contractId } },
      }),
    ),
  );
}

export function useDeleteContract(orgId: string, contractId: string) {
  const api = useApi();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () =>
      unwrap(
        api.DELETE("/organizations/{org_id}/contracts/{contract_id}", {
          params: { path: { org_id: orgId, contract_id: contractId } },
        }),
      ),
    onSuccess: () => {
      // The open contract page is still mounted until the redirect: don't refetch the
      // contract or its documents (they are gone), only mark them stale.
      const gone = (key: readonly unknown[]) =>
        (key[2] === "contracts" && key[3] === contractId) || key[2] === "documents";
      void qc.invalidateQueries({ queryKey: ["org", orgId], refetchType: "none" });
      return qc.invalidateQueries({
        queryKey: ["org", orgId],
        predicate: (q) => !gone(q.queryKey),
      });
    },
  });
}

export function useUpdateDateRule(orgId: string) {
  return useContractMutation(
    orgId,
    (api, { id, body }: { id: string; body: Schemas["DateRuleUpdate"] }) =>
      unwrap(
        api.PATCH("/organizations/{org_id}/date-rules/{rule_id}", {
          params: { path: { org_id: orgId, rule_id: id } },
          body,
        }),
      ),
  );
}

export function useCreateDateRule(orgId: string, contractId: string) {
  return useContractMutation(orgId, (api, body: Schemas["DateRuleIn"]) =>
    unwrap(
      api.POST("/organizations/{org_id}/contracts/{contract_id}/date-rules", {
        params: { path: { org_id: orgId, contract_id: contractId } },
        body,
      }),
    ),
  );
}

export function useUpdatePaymentTerm(orgId: string) {
  return useContractMutation(
    orgId,
    (api, { id, body }: { id: string; body: Schemas["PaymentTermUpdate"] }) =>
      unwrap(
        api.PATCH("/organizations/{org_id}/payment-terms/{term_id}", {
          params: { path: { org_id: orgId, term_id: id } },
          body,
        }),
      ),
  );
}

export function useUpdateDeadline(orgId: string) {
  return useContractMutation(
    orgId,
    (api, { id, ...body }: { id: string } & Schemas["DeadlineUpdate"]) =>
      unwrap(
        api.PATCH("/organizations/{org_id}/deadlines/{deadline_id}", {
          params: { path: { org_id: orgId, deadline_id: id } },
          body,
        }),
      ),
  );
}

// ---- Notifications, preferences, reminders, calendar ----

export function useNotifications(orgId: string) {
  const api = useApi();
  return useQuery({
    queryKey: ["org", orgId, "notifications"],
    queryFn: () =>
      unwrap(
        api.GET("/organizations/{org_id}/notifications", {
          params: { path: { org_id: orgId }, query: { limit: 30 } },
        }),
      ),
    refetchInterval: 60_000,
  });
}

export function useMarkNotificationsRead(orgId: string) {
  return useContractMutation(orgId, (api, ids: string[] | null) =>
    unwrap(
      api.POST("/organizations/{org_id}/notifications/read", {
        params: { path: { org_id: orgId } },
        body: { ids },
      }),
    ),
  );
}

export function usePreferences(orgId: string) {
  const api = useApi();
  return useQuery({
    queryKey: ["org", orgId, "preferences"],
    queryFn: () =>
      unwrap(
        api.GET("/organizations/{org_id}/me/preferences", { params: { path: { org_id: orgId } } }),
      ),
  });
}

export function useUpdatePreferences(orgId: string) {
  return useContractMutation(orgId, (api, body: Schemas["PreferencesUpdate"]) =>
    unwrap(
      api.PATCH("/organizations/{org_id}/me/preferences", {
        params: { path: { org_id: orgId } },
        body,
      }),
    ),
  );
}

export function useReminderSettings(orgId: string) {
  const api = useApi();
  return useQuery({
    queryKey: ["org", orgId, "reminder-settings"],
    queryFn: () =>
      unwrap(
        api.GET("/organizations/{org_id}/reminder-settings", {
          params: { path: { org_id: orgId } },
        }),
      ),
  });
}

export function useUpdateReminderSettings(orgId: string) {
  return useContractMutation(orgId, (api, body: Schemas["ReminderSettings"]) =>
    unwrap(
      api.PUT("/organizations/{org_id}/reminder-settings", {
        params: { path: { org_id: orgId } },
        body,
      }),
    ),
  );
}

export function useCalendarFeed(orgId: string) {
  const api = useApi();
  return useQuery({
    queryKey: ["org", orgId, "calendar-feed"],
    queryFn: () =>
      unwrap(
        api.GET("/organizations/{org_id}/calendar-feed", { params: { path: { org_id: orgId } } }),
      ),
  });
}

export function useCreateCalendarFeed(orgId: string) {
  return useContractMutation<void>(orgId, (api) =>
    unwrap(
      api.POST("/organizations/{org_id}/calendar-feed", { params: { path: { org_id: orgId } } }),
    ),
  );
}

export function useDeleteCalendarFeed(orgId: string) {
  return useContractMutation<void>(orgId, (api) =>
    unwrap(
      api.DELETE("/organizations/{org_id}/calendar-feed", { params: { path: { org_id: orgId } } }),
    ),
  );
}

// ---- Chat ----

export function useChatThreads(
  orgId: string,
  query: { workspace_id?: string; contract_id?: string },
) {
  const api = useApi();
  return useQuery({
    queryKey: ["org", orgId, "chat", "threads", query],
    queryFn: () =>
      unwrap(
        api.GET("/organizations/{org_id}/chat/threads", {
          params: { path: { org_id: orgId }, query },
        }),
      ),
  });
}

export function useChatThread(orgId: string, threadId: string | null) {
  const api = useApi();
  return useQuery({
    queryKey: ["org", orgId, "chat", "thread", threadId],
    enabled: !!threadId,
    queryFn: () =>
      unwrap(
        api.GET("/organizations/{org_id}/chat/threads/{thread_id}", {
          params: { path: { org_id: orgId, thread_id: threadId! } },
        }),
      ),
  });
}

export function useCreateChatThread(orgId: string) {
  return useContractMutation(orgId, (api, body: Schemas["ThreadCreate"]) =>
    unwrap(
      api.POST("/organizations/{org_id}/chat/threads", {
        params: { path: { org_id: orgId } },
        body,
      }),
    ),
  );
}

export function useDeleteChatThread(orgId: string) {
  return useContractMutation(orgId, (api, threadId: string) =>
    unwrap(
      api.DELETE("/organizations/{org_id}/chat/threads/{thread_id}", {
        params: { path: { org_id: orgId, thread_id: threadId } },
      }),
    ),
  );
}

export type ChatEvent =
  | { type: "delta"; text: string }
  | { type: "message"; message: Schemas["MessageOut"] }
  | { type: "error"; detail: string; message?: Schemas["MessageOut"] };

/** POST a question and stream the answer (Server-Sent Events over fetch). */
export function useSendChatMessage(orgId: string) {
  const auth = useAuthState();
  const qc = useQueryClient();
  return async (threadId: string, text: string, onEvent: (e: ChatEvent) => void) => {
    try {
      const res = await fetch(
        `${API_URL}/organizations/${orgId}/chat/threads/${threadId}/messages`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json", ...(await auth.getHeaders()) },
          body: JSON.stringify({ text }),
        },
      );
      if (!res.ok || !res.body) {
        const body = await res.json().catch(() => null);
        onEvent({ type: "error", detail: body?.detail ?? `Request failed (${res.status})` });
        return;
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        let split;
        while ((split = buffer.indexOf("\n\n")) >= 0) {
          const chunk = buffer.slice(0, split);
          buffer = buffer.slice(split + 2);
          for (const line of chunk.split("\n")) {
            if (line.startsWith("data: ")) onEvent(JSON.parse(line.slice(6)) as ChatEvent);
          }
        }
      }
    } catch (e) {
      onEvent({ type: "error", detail: e instanceof Error ? e.message : "Network error" });
    } finally {
      await qc.invalidateQueries({ queryKey: ["org", orgId, "chat"] });
    }
  };
}

// ---- Downloads and drafting ----

/** Fetch a file with auth headers and save it via a temporary link. */
export function useDownload(orgId: string) {
  const auth = useAuthState();
  return useMutation({
    mutationFn: async ({
      path,
      filename,
      body,
    }: {
      path: string;
      filename: string;
      body?: unknown;
    }) => {
      const res = await fetch(`${API_URL}/organizations/${orgId}${path}`, {
        method: body ? "POST" : "GET",
        headers: {
          ...(body ? { "Content-Type": "application/json" } : {}),
          ...(await auth.getHeaders()),
        },
        body: body ? JSON.stringify(body) : undefined,
      });
      if (!res.ok) throw new ApiError(res.status, "Download failed");
      const url = URL.createObjectURL(await res.blob());
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 10_000);
    },
  });
}

export type DraftEvent =
  | { type: "delta"; text: string }
  | { type: "done"; text: string; citations: Schemas["Citation"][] }
  | { type: "error"; detail: string };

async function readSse<T>(res: Response, onEvent: (e: T) => void) {
  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let split;
    while ((split = buffer.indexOf("\n\n")) >= 0) {
      const chunk = buffer.slice(0, split);
      buffer = buffer.slice(split + 2);
      for (const line of chunk.split("\n")) {
        if (line.startsWith("data: ")) onEvent(JSON.parse(line.slice(6)) as T);
      }
    }
  }
}

/** Stream an AI-drafted notice letter. */
export function useDraftNotice(orgId: string, contractId: string) {
  const auth = useAuthState();
  return async (body: Schemas["DraftNoticeIn"], onEvent: (e: DraftEvent) => void) => {
    try {
      const res = await fetch(
        `${API_URL}/organizations/${orgId}/contracts/${contractId}/draft-notice`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json", ...(await auth.getHeaders()) },
          body: JSON.stringify(body),
        },
      );
      if (!res.ok || !res.body) {
        const err = await res.json().catch(() => null);
        onEvent({ type: "error", detail: err?.detail ?? `Request failed (${res.status})` });
        return;
      }
      await readSse<DraftEvent>(res, onEvent);
    } catch (e) {
      onEvent({ type: "error", detail: e instanceof Error ? e.message : "Network error" });
    }
  };
}

// ---- Manual entry ----

/** Server feature flags (whether AI analysis is configured). */
export function useConfig() {
  const api = useApi();
  return useQuery({
    queryKey: ["config"],
    queryFn: () => unwrap(api.GET("/config")) as Promise<{ ai_enabled: boolean }>,
    staleTime: 5 * 60_000,
  });
}

export function useAiEnabled(): boolean | undefined {
  return useConfig().data?.ai_enabled;
}

export function useCreateContractManually(orgId: string, workspaceId: string) {
  return useContractMutation(orgId, (api, body: Schemas["ContractCreate"]) =>
    unwrap(
      api.POST("/organizations/{org_id}/workspaces/{workspace_id}/contracts/manual", {
        params: { path: { org_id: orgId, workspace_id: workspaceId } },
        body,
      }),
    ),
  );
}

/** Add the ready-made example contract (with a signed copy) to a workspace. */
export function useCreateSampleContract(orgId: string) {
  return useContractMutation(orgId, (api, workspaceId: string) =>
    unwrap(
      api.POST("/organizations/{org_id}/workspaces/{workspace_id}/contracts/sample", {
        params: { path: { org_id: orgId, workspace_id: workspaceId } },
      }),
    ),
  );
}

export function useCreatePaymentTerm(orgId: string, contractId: string) {
  return useContractMutation(orgId, (api, body: Schemas["PaymentTermIn"]) =>
    unwrap(
      api.POST("/organizations/{org_id}/contracts/{contract_id}/payment-terms", {
        params: { path: { org_id: orgId, contract_id: contractId } },
        body,
      }),
    ),
  );
}

/** Attach a file to an existing contract (multipart). */
export function useAttachDocument(orgId: string) {
  const auth = useAuthState();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ contractId, file }: { contractId: string; file: File }) => {
      const form = new FormData();
      form.append("file", file);
      const res = await fetch(
        `${API_URL}/organizations/${orgId}/contracts/${contractId}/documents`,
        {
          method: "POST",
          body: form,
          headers: await auth.getHeaders(),
        },
      );
      const body = await res.json().catch(() => null);
      if (!res.ok) {
        const detail = body?.detail;
        throw new ApiError(res.status, typeof detail === "object" ? detail.message : detail);
      }
      return body as Schemas["ContractDetail"];
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["org", orgId] }),
  });
}

// ---- Amendments ----

export function useCreateAmendment(orgId: string, contractId: string) {
  return useContractMutation(orgId, (api, body: Schemas["AmendmentCreate"]) =>
    unwrap(
      api.POST("/organizations/{org_id}/contracts/{contract_id}/amendments", {
        params: { path: { org_id: orgId, contract_id: contractId } },
        body,
      }),
    ),
  );
}

export function useDeleteAmendment(orgId: string) {
  return useContractMutation(orgId, (api, amendmentId: string) =>
    unwrap(
      api.DELETE("/organizations/{org_id}/amendments/{amendment_id}", {
        params: { path: { org_id: orgId, amendment_id: amendmentId } },
      }),
    ),
  );
}

/** Attach the amendment's document (multipart). */
export function useAttachAmendmentDocument(orgId: string) {
  const auth = useAuthState();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ amendmentId, file }: { amendmentId: string; file: File }) => {
      const form = new FormData();
      form.append("file", file);
      const res = await fetch(
        `${API_URL}/organizations/${orgId}/amendments/${amendmentId}/documents`,
        { method: "POST", body: form, headers: await auth.getHeaders() },
      );
      const body = await res.json().catch(() => null);
      if (!res.ok) {
        const detail = body?.detail;
        throw new ApiError(res.status, typeof detail === "object" ? detail.message : detail);
      }
      return body as Schemas["AmendmentOut"];
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["org", orgId] }),
  });
}
