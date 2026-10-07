import type { Schemas } from "@contraict/api-client";

export const ORG_KIND_LABELS: Record<Schemas["OrganizationKind"], string> = {
  company: "Company",
  holding: "Holding company",
  law_firm: "Law firm",
};

export const WORKSPACE_KIND_LABELS: Record<Schemas["WorkspaceKind"], string> = {
  client: "Client",
  entity: "Legal entity",
  department: "Department",
};

/** What a workspace is called for each kind of organization. */
export const DEFAULT_WORKSPACE_KIND: Record<Schemas["OrganizationKind"], Schemas["WorkspaceKind"]> =
  {
    company: "department",
    holding: "entity",
    law_firm: "client",
  };

export const ORG_ROLE_LABELS: Record<Schemas["OrgRole"], string> = {
  owner: "Owner",
  admin: "Admin",
  member: "Member",
};

export const WORKSPACE_ROLE_LABELS: Record<Schemas["WorkspaceRole"], string> = {
  admin: "Admin",
  editor: "Editor",
  viewer: "Viewer",
};
