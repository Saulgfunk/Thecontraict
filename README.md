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

**Phase 0 (foundations) done:** organizations, workspaces (client / entity / department,
nestable), members and roles, tenant isolation with PostgreSQL Row-Level Security, audit
log, deterministic deadline engine (business days, public holidays, auto-renewals,
deemed receipt) with a calculator in the UI.

**Next (Phase 1):** contract upload, parsing/OCR, AI extraction with clause citations,
review screen, deadlines and reminders. See [docs/roadmap.md](docs/roadmap.md).
