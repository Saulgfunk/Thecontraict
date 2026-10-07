"use client";

import { createApiClient, unwrap, type ApiClient, type Schemas } from "@contraict/api-client";
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
