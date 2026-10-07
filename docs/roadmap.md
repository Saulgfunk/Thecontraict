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
- Deadlines list, countdowns, owners, done/reopen. (Calendar grid view and renew/terminate decision records: Phase 2.)
- Email + in-app reminders, iCal feed, weekly digest.
- Payment schedule + reminders.
- AI chat (contract & workspace scope) with citations.
- Audit log. (Extraction eval set and accuracy dashboard: next, needs real contracts and an API key.)

## Phase 2 — Depth

- Contract families and amendment-aware "effective terms".
- Obligations tracking, risk flags, contract summaries, notice letter drafting.
- Portfolio dashboards, Excel/PDF exports, client reports (law firms).
- Email-in ingestion, Google Drive / OneDrive / DocuSign import.
- Slack / Teams notifications, SSO (SAML).

## Phase 3 — Mobile & integrations

- Expo mobile app: deadlines, alerts (push), contract viewer, chat, quick upload via camera.
- Invoice upload & matching; accounting integrations; cash-flow forecast.
- Playbook review of incoming contracts.
- Client portal (law firms), SCIM.

## Phase 4 — Scale

- Data residency (regional deployments), additional contract languages, public API & webhooks.
