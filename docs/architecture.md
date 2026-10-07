# Architecture & Tech Stack (proposal)

## 1. Guiding decisions

1. **Web first, mobile next, one API.** A single typed HTTP API serves the web app now and
   the mobile app later. An OpenAPI spec generates a TypeScript client shared by both.
2. **Python backend.** Document parsing, OCR, date arithmetic, holiday calendars and AI
   tooling are strongest in Python.
3. **TypeScript frontends.** React for web (Next.js) and React Native (Expo) for mobile, so
   UI logic, types and the API client are shared.
4. **LLM extracts, code computes.** The model reads clauses and returns structured rules;
   deadlines are calculated by deterministic, unit-tested code.
5. **Every AI output is traceable** to a clause/page and is reviewable by a human.
6. **Tenant isolation by design** (organization + workspace scoping enforced in the DB).

## 2. Proposed stack

| Layer            | Choice                                                                                                                                | Why                                                                       |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------- |
| Monorepo         | **pnpm + Turborepo** (JS apps/packages) with a Python `api/` service                                                                  | One repo, shared types, single CI                                         |
| Web app          | **Next.js (App Router) + TypeScript + Tailwind CSS + shadcn/ui**                                                                      | Mature, fast to build, good table/form/calendar ecosystem                 |
| Data fetching    | **TanStack Query** + generated OpenAPI client                                                                                         | Same client reused in mobile                                              |
| PDF viewer       | **PDF.js** (react-pdf) with highlight overlays                                                                                        | Jump-to-clause citations                                                  |
| Mobile (Phase 3) | **Expo / React Native**                                                                                                               | Shares TS code; push notifications via Expo                               |
| API              | **Python 3.12 + FastAPI + Pydantic v2**                                                                                               | Typed, auto OpenAPI, async                                                |
| ORM / migrations | **SQLAlchemy 2.0 + Alembic**                                                                                                          | Standard, supports RLS session vars                                       |
| Database         | **PostgreSQL 16 + pgvector**                                                                                                          | Relational core + vector search in one DB; Row-Level Security for tenancy |
| Background jobs  | **Celery + Redis** (Celery Beat for schedules)                                                                                        | Document pipeline, reminder scheduler, digests                            |
| File storage     | **S3-compatible object storage** (AWS S3; MinIO locally)                                                                              | Encrypted, presigned uploads                                              |
| Document parsing | **Docling** (PDF/DOCX layout, tables, OCR) — cloud OCR (AWS Textract) as fallback for poor scans                                      | Layout-aware clause segmentation with page coordinates                    |
| LLM              | **Anthropic Claude API** — `claude-opus-5-5`                                                                                          | Long-context document understanding, structured outputs, native citations |
| Embeddings       | **Voyage AI** (e.g. `voyage-law` family) → pgvector                                                                                   | Legal-tuned retrieval for chat across many contracts                      |
| Date logic       | `python-dateutil`, `holidays` package, custom rule engine                                                                             | Deterministic, testable deadline computation                              |
| Auth             | **Clerk** (email, Google/Microsoft, MFA, orgs; SAML SSO on paid plans) — WorkOS as alternative if enterprise SSO/SCIM becomes primary | Works with Next.js and Expo; JWT verified by FastAPI                      |
| Email            | **Postmark** (transactional)                                                                                                          | High deliverability for deadline alerts                                   |
| Calendar         | iCal (`.ics`) feed per user (`icalendar` lib)                                                                                         | Works with every calendar app                                             |
| Observability    | **Sentry** + OpenTelemetry; structured logs                                                                                           | Errors + tracing across API/workers                                       |
| Testing          | pytest, Vitest, Playwright; **AI extraction eval set**                                                                                | Regression-test extraction accuracy                                       |
| Infra            | Docker; local `docker compose`; prod on **AWS** (ECS Fargate, RDS Postgres, ElastiCache, S3, KMS) via Terraform                       | Region-per-deployment possible later for data residency                   |
| CI/CD            | GitHub Actions                                                                                                                        | Lint, typecheck, tests, evals, deploy                                     |

## 3. System overview

```
 Browser (Next.js)          Mobile (Expo, later)
        │                           │
        └──────────► FastAPI ◄──────┘   (JWT from Clerk; org/workspace scoping)
                       │  │
        ┌──────────────┘  └──────────────┐
        ▼                                ▼
  PostgreSQL + pgvector            S3 (documents)
        ▲                                ▲
        │                                │
   Celery workers ◄──── Redis ────► Celery Beat (reminders, digests)
        │
        ├─ Parse/OCR (Docling / Textract)
        ├─ Segment into clauses (with page + bbox)
        ├─ Claude: structured extraction
        ├─ Rule engine: compute deadlines
        ├─ Voyage: embeddings
        └─ Notifications (Postmark, in-app, push)
```

## 4. Document processing pipeline

1. **Upload** — browser gets a presigned S3 URL; API creates `Document` (status `uploaded`).
2. **Parse** — Docling extracts text with page numbers and bounding boxes; OCR for scans.
3. **Segment** — split into numbered clauses/sections (`Clause` rows), keep page/bbox for highlighting.
4. **Classify** — document type (MSA, lease, NDA, SOW, amendment…) and whether it amends another contract.
5. **Extract** — Claude (`claude-opus-5-5`, adaptive thinking) with **structured outputs**
   (`output_config.format`, JSON schema) returns metadata, date rules, payment terms,
   obligations and risk flags. Each item must reference clause IDs we supplied in the prompt,
   which gives us citations while still using a strict schema (the API's native citations
   feature is incompatible with structured outputs, so it is reserved for chat).
6. **Compute** — rule engine turns rules into concrete dates (calendar/business days,
   holiday calendar of governing-law country, deemed-receipt rules), storing the derivation.
7. **Embed** — clause embeddings for retrieval.
8. **Review** — items appear as `ai_suggested`; users confirm/edit. Only confirmed (or
   high-confidence, if the org opts in) deadlines drive reminders.

Long documents fit in Claude's 1M context; system prompt and schema are prompt-cached.
Bulk imports can use the Message Batches API (50% cost, asynchronous).

## 5. AI chat

- Retrieval: hybrid search (Postgres full-text + pgvector) restricted to workspaces the user can access.
- Answer generation: Claude with retrieved clauses passed as `document` blocks with
  **citations enabled**, streamed to the UI; citations map back to clause/page for highlighting.
- Single-contract chat can pass the whole document (no retrieval needed).
- Tools (later): query the structured DB ("list contracts expiring in Q1 with value > €100k"),
  draft notice letters.
- Guardrail: answer only from provided documents; say "not found" otherwise.

## 6. Multi-tenancy & security

- Every row carries `organization_id`; contract-related rows also `workspace_id`.
- PostgreSQL **Row-Level Security** keyed on per-request session variables
  (`app.org_id`, `app.workspace_ids`) as defence-in-depth behind API authorization.
- S3 keys prefixed by org; SSE-KMS encryption.
- Audit log table (append-only).
- Anthropic API: commercial terms (no training on customer data); evaluate zero-data-retention.

## 7. Repository layout (planned)

```
apps/
  web/            Next.js app
  mobile/         Expo app (Phase 3)
packages/
  api-client/     generated TS client from OpenAPI
  ui/             shared React components / design tokens
services/
  api/            FastAPI app, SQLAlchemy models, Alembic migrations
    app/
      routers/  models/  schemas/  services/
      pipeline/   parse, segment, extract, compute, embed
      deadlines/  rule engine + holiday calendars
      workers/    Celery tasks & beat schedule
    tests/
    evals/        extraction accuracy test set
infra/            docker-compose, Terraform
docs/
```
