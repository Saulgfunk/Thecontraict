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

export const CONTRACT_STATUS: Record<
  Schemas["ContractStatus"],
  { label: string; tone: "neutral" | "primary" | "warning" | "success" | "danger" }
> = {
  processing: { label: "Analysing", tone: "primary" },
  needs_review: { label: "Needs review", tone: "warning" },
  active: { label: "Active", tone: "success" },
  expired: { label: "Expired", tone: "neutral" },
  terminated: { label: "Terminated", tone: "neutral" },
};

export const RULE_TYPE_LABELS: Record<Schemas["DateRuleType"], string> = {
  non_renewal_notice: "Notice of non-renewal",
  termination_notice: "Termination notice",
  option_exercise: "Option window",
  price_review: "Price review",
  warranty_end: "Warranty ends",
  insurance_expiry: "Insurance expires",
  guarantee_expiry: "Guarantee expires",
  lock_in_end: "Lock-in ends",
  other: "Other",
};

export const ANCHOR_LABELS: Record<Schemas["DateAnchor"], string> = {
  term_end: "end of the current term",
  term_start: "start of the current term",
  effective_date: "effective date",
  fixed_date: "a fixed date",
};

export const DEADLINE_KIND_LABELS: Record<Schemas["DeadlineKind"], string> = {
  term_end: "Term",
  notice: "Notice",
  option: "Option",
  price_review: "Price review",
  payment: "Payment",
  other: "Other",
};

export const FREQUENCY_LABELS: Record<Schemas["PaymentFrequency"], string> = {
  one_off: "One-off",
  monthly: "Monthly",
  quarterly: "Quarterly",
  semi_annual: "Every 6 months",
  annual: "Annual",
  other: "Other",
};

export const PAYMENT_DIRECTION_LABELS: Record<Schemas["PaymentDirection"], string> = {
  payable: "We pay",
  receivable: "We receive",
  unknown: "Direction unknown",
};
