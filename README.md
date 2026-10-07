# TheContrAIct

AI-powered contract lifecycle assistant for in-house legal teams, holding companies,
mid-size companies and law firms managing contracts for multiple clients.

Upload contracts → extract key dates, notice periods, payment terms and obligations
(with clause citations) → get alerted before deadlines → ask an AI assistant anything
about your contract portfolio.

## Documentation

| Document                                     | Contents                              |
| -------------------------------------------- | ------------------------------------- |
| [docs/product-spec.md](docs/product-spec.md) | Target users, feature set, MVP scope  |
| [docs/architecture.md](docs/architecture.md) | Proposed tech stack and system design |
| [docs/data-model.md](docs/data-model.md)     | Core entities and relationships       |
| [docs/roadmap.md](docs/roadmap.md)           | Phased delivery plan                  |

## Repository layout

| Path                  | What                                                  |
| --------------------- | ----------------------------------------------------- |
| `apps/web`            | Next.js web app                                       |
| `packages/api-client` | TypeScript API client generated from the OpenAPI spec |
| `services/api`        | FastAPI service, database models, migrations, workers |
| `infra/`              | Local infrastructure helpers                          |
| `docs/`               | Product and technical documentation                   |

## Getting started

Requirements: Node 22 + pnpm 10, Python 3.12 + [uv](https://docs.astral.sh/uv/), Docker.

```bash
docker compose up -d                 # Postgres (pgvector), Redis, MinIO

cd services/api
cp .env.example .env
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload # http://localhost:8000/docs

cd ../../apps/web
cp .env.example .env.local
cd ../.. && pnpm install && pnpm dev # http://localhost:3000
```

Locally both apps run in **dev auth mode**: sign in with any email. Switch to Clerk by
setting `AUTH_MODE=clerk` (API) and `NEXT_PUBLIC_AUTH_MODE=clerk` (web) — see
`apps/web/README.md`.

After changing API endpoints, regenerate the TypeScript client: `pnpm api:openapi`.

## Checks

```bash
pnpm format:check && pnpm lint && pnpm typecheck && pnpm build     # web
cd services/api && uv run ruff check . && uv run mypy app && uv run pytest   # api
```

CI runs all of these on every pull request (`.github/workflows/ci.yml`).

## Status

**Phase 0 (foundations):** organizations, workspaces (client / entity / department,
nestable), members and roles, tenant isolation with PostgreSQL Row-Level Security, audit
log, deterministic deadline engine with a calculator in the UI.

**Phase 1 (MVP):**

- Contract upload (PDF, Word, scanned PDFs), clause segmentation, AI extraction with
  Claude (terms, notice periods and key dates, payment terms — each citing its clauses).
- Review screen with side-by-side clause viewer; deadline calculation from the extracted
  rules (renewals, business days, holidays, deemed receipt); payment schedules.
- Deadlines view across workspaces; reminders (in-app + email) on a configurable
  schedule to each contract's owner; weekly digest; private iCal calendar feed.
- AI chat per contract and per workspace, with answers citing the exact clauses.

**Phase 2 (in progress):** decisions on deadlines, calendar view, AI-drafted notice
letters (download as Word), Excel exports of contracts and deadlines.

AI analysis and chat need `ANTHROPIC_API_KEY` in `services/api/.env`. To try the AI on
sample or real contracts without running the app, see
[services/api/evals/README.md](services/api/evals/README.md). Without a worker
running, set `TASKS_EAGER=true` so uploads are processed by the API process itself.
Reminders and digests run on Celery beat:

```bash
cd services/api
uv run celery -A app.workers.celery_app worker -l info
uv run celery -A app.workers.celery_app beat -l info
```

Emails are printed to the log by default (`EMAIL_BACKEND=console`); set `smtp` or
`postmark` in `services/api/.env` to send them.
