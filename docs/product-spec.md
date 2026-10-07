# Product Specification

## 1. Target users

| Segment | Typical need | Product implication |
|---|---|---|
| **In-house legal teams** | Never miss a renewal/notice deadline; answer business questions about contracts fast | Deadline ownership, approvals, audit trail, playbook review |
| **Holding companies** | Visibility across many subsidiaries/entities | Entity hierarchy, consolidated dashboards, per-entity access |
| **Mid-size companies** (procurement, finance, ops) | Control auto-renewals and spend, invoice timing | Invoice/payment calendar, spend views, simple UX |
| **Law firms with multiple clients** | Manage contracts *on behalf of* clients, strict separation between clients | Client workspaces, ethical walls, client-facing reports, optional client portal |

Common requirements across all segments: multi-user, role-based access, strong
confidentiality, accurate dates with verifiable sources, worldwide (time zones,
public holidays, currencies) — contracts in **English only** for v1.

## 2. Organising principle: Organization → Workspace → Contract

- **Organization** — the paying tenant (a company, a holding group, a law firm).
- **Workspace** — a hard access boundary inside the organization. Its meaning depends on the customer:
  - law firm → a **client** (or client matter)
  - holding company → a **legal entity / subsidiary** (workspaces can be nested)
  - company → a **department or business unit**
- **Contract** — belongs to exactly one workspace; grouped into **contract families**
  (master agreement + amendments + SOWs + side letters).

Users only see workspaces they are members of (ethical walls for law firms).
Org admins get a consolidated cross-workspace view.

## 3. Feature set

### 3.1 Ingestion
- Upload PDF (native and scanned → OCR), DOCX, images; bulk upload / zip import.
- Email-in address per workspace (forward contracts and attachments).
- Duplicate and version detection; link amendments to their parent contract.
- Later: Google Drive, OneDrive/SharePoint, Box, Dropbox, DocuSign/Adobe Sign import.

### 3.2 AI extraction (with clause citations)
- **Metadata:** parties, counterparty, contract type, effective date, term, value, currency,
  governing law, jurisdiction, signatories, notice address(es).
- **Key dates & periods:** expiry, auto-renewal terms, notice of non-renewal, termination
  notice, option windows (extension/purchase), price review/indexation dates, warranty
  expiry, insurance/guarantee/bond expiry, lock-in periods, post-termination obligations
  (confidentiality, non-compete, data return).
- **Payment terms:** billing frequency, amounts, payment terms (net X), escalation/indexation,
  late interest, discounts.
- **Obligations:** recurring duties for either party (reports, audits, deliveries).
- **Risk flags:** unlimited liability, long auto-renewal + long notice, one-sided termination,
  missing data-protection terms, unusual governing law.
- Every extracted value carries: **source clause + page**, **confidence**, and a
  **status** (`ai_suggested` → `confirmed` / `edited` / `rejected`).
- Deadlines are **computed deterministically in code** from extracted rules
  (e.g. `term_end − 90 calendar days`), with the derivation shown to the user.
  Supports calendar vs. business days, country holiday calendars, and deemed-receipt rules.
- Amendments override the clauses they amend ("effective terms" view).

### 3.3 Deadlines & alerts
- Countdown in days / weeks / months, colour-coded urgency.
- Reminder schedules per deadline type (default e.g. 120/90/60/30/14/7/1 days) and per user.
- Channels: in-app, email, mobile push (with mobile app), Slack/Teams (later), SMS (later).
- Calendar sync via personal iCal feed (Google/Outlook/Apple) — later two-way sync.
- **Ownership & escalation:** each deadline has an owner and backup; unacknowledged alerts
  escalate.
- **Decision workflow:** Renew / Renegotiate / Terminate / Let expire; attach evidence
  (sent notice letter). A deadline closes only with a recorded decision.
- Snooze with reason; everything audit-logged.
- Weekly digest email per user and per workspace.

### 3.4 Invoicing & payments
- Payment schedule generated from contract terms (receivable and payable).
- Alerts for invoices to issue / expected invoices / payment due dates.
- Price escalation calculator (fixed % and index-linked, e.g. CPI).
- Later: invoice upload & matching against contract rates; accounting integrations
  (Xero, QuickBooks, NetSuite, SAP); cash-flow forecast.

### 3.5 AI assistant (chat)
- Ask about one contract, a contract family, a workspace, or (for admins) the whole portfolio.
- Every answer cites the clauses it relies on (click → jump to highlighted text).
- Says explicitly when the documents don't answer the question.
- Cross-contract queries: "Which supplier contracts allow termination for convenience?"
- Comparison: "Compare liability caps across these 4 contracts."
- Drafting: non-renewal / termination notices, renegotiation emails pre-filled with the
  correct clause references and notice address.
- Contract summaries (one-page brief) and pre-renewal negotiation briefings.
- Later: playbook review of incoming contracts against the organization's standard positions.

### 3.6 Portfolio, search & reporting
- Contract table with filters (type, counterparty, workspace, value, status, next deadline).
- Full-text + semantic search.
- Timeline/calendar view of all deadlines.
- Dashboards: upcoming deadlines, auto-renewals about to lock in, contract value by
  category/counterparty/entity, missed/near-miss deadlines.
- Export to Excel/PDF; client-ready reports for law firms.

### 3.7 Administration, security & compliance
- Roles: Org Admin, Workspace Admin, Editor, Viewer, (later) External Client Viewer.
- SSO (SAML/OIDC) and MFA; SCIM provisioning (later).
- Full audit log (views, edits, confirmations, exports).
- Encryption in transit and at rest; customer data never used for model training.
- Data retention / deletion controls.
- Data residency (EU/US/…) — architecture must allow it; not required for v1.

## 4. MVP scope (Phase 1 — web)

1. Organizations, workspaces, users, roles, email+password and Google/Microsoft login.
2. Upload PDF/DOCX (incl. OCR for scans); document viewer.
3. AI extraction of metadata, key dates, notice periods and payment terms, with citations
   and confidence.
4. Review & confirm screen.
5. Deterministic deadline computation (calendar/business days, holidays).
6. Deadline list + calendar view with countdowns; owners.
7. Email reminders + in-app notifications; iCal feed.
8. Payment/invoice schedule and reminders.
9. AI chat over a contract / workspace with clause citations.
10. Audit log (basic).

Out of MVP: mobile app, integrations, invoice matching, playbooks, obligations tracking,
client portal, SSO/SCIM, non-English contracts.

## 5. Success metrics
- Extraction accuracy on key dates (target ≥ 95% precision on confirmed set).
- % of AI-suggested dates confirmed without edits.
- Time from upload to confirmed deadlines.
- Deadlines acted on before due date (and missed deadlines → 0).
