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
import { createContext, useContext, useEffect, useMemo, useState } from "react";

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
  // Never show one user's cached data to another after switching accounts.
  const userKey = auth.status === "signed-in" ? auth.email : null;
  useEffect(() => {
    queryClient.clear();
  }, [userKey, queryClient]);
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
  return useContractMutation<void>(orgId, (api) =>
    unwrap(
      api.DELETE("/organizations/{org_id}/contracts/{contract_id}", {
        params: { path: { org_id: orgId, contract_id: contractId } },
      }),
    ),
  );
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
    (api, { id, status }: { id: string; status: Schemas["DeadlineStatus"] }) =>
      unwrap(
        api.PATCH("/organizations/{org_id}/deadlines/{deadline_id}", {
          params: { path: { org_id: orgId, deadline_id: id } },
          body: { status },
        }),
      ),
  );
}
