# Roadmap

## Phase 0 — Foundations

- Monorepo scaffold (Next.js web, FastAPI api, shared packages), docker compose (Postgres, Redis, MinIO).
- Auth (Clerk), organizations, workspaces, memberships, RLS.
- CI: lint, typecheck, tests.

## Phase 1 — MVP (web) — done, except where noted

- Upload + parsing/OCR + clause segmentation + document viewer.
- Claude extraction (metadata, date rules, payment terms) with clause citations.
- Deadline rule engine (calendar/business days, holidays) + derivation text.
- Review & confirm UI.
- Deadlines list and calendar view, countdowns, owners, done/reopen, decisions (renew / renegotiate / terminate / let expire / exercise option) with notes.
- Email + in-app reminders, iCal feed, weekly digest.
- Payment schedule + reminders.
- AI chat (contract & workspace scope) with citations.
- Audit log. (Extraction eval set and accuracy dashboard: next, needs real contracts and an API key.)

## Phase 2 — Depth

- Done: AI-drafted notices (non-renewal, termination, renegotiation, option exercise) with
  Word download; Excel exports of contracts and deadlines.
- Done: amendments (recorded changes to terms with before/after history, applied to the
  current terms, reversible; amendment documents kept alongside).
- Done: simpler UI after a competitor review (ContractSafe, Juro, Concord, Zefort): home
  page of what needs attention in plain sentences with one-click decisions and undo; one
  Contracts list across workspaces with search; contract page led by an "At a glance"
  summary with details in tabs; a short new-contract form with "More options"; four menu
  items (Home, Contracts, Deadlines, Settings).
- Next for simplicity: a sample contract to explore; reminders to people without a login;
  auto-creating the first workspace for single companies; finding contracts with no
  reminders or no signed copy.
- Next for amendments: AI reading of amendment documents to propose the changes;
  side letters and SOWs as linked documents.
- Obligations tracking, risk flags.
- Portfolio dashboards, PDF client reports (law firms).
- Email-in ingestion, Google Drive / OneDrive / DocuSign import.
- Slack / Teams notifications, SSO (SAML).

## Phase 3 — Mobile & integrations

- Expo mobile app: deadlines, alerts (push), contract viewer, chat, quick upload via camera.
- Invoice upload & matching; accounting integrations; cash-flow forecast.
- Playbook review of incoming contracts.
- Client portal (law firms), SCIM.

## Phase 4 — Scale

- Data residency (regional deployments), additional contract languages, public API & webhooks.
