# TheContrAIct API

FastAPI service: tenancy (organizations, workspaces, memberships), audit log, deadline
engine, and (next) the document pipeline and AI extraction.

## Run locally

```bash
uv sync
cp .env.example .env
uv run alembic upgrade head
uv run uvicorn app.main:app --reload        # http://localhost:8000/docs
uv run celery -A app.workers.celery_app worker -l info   # background worker
```

Postgres, Redis and MinIO come from `docker compose up -d` at the repo root.

## Checks

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy app
uv run pytest            # needs Postgres; uses the contraict_test database
```

The test database role must **not** be a superuser: superusers bypass Row-Level
Security, and the tenant-isolation tests would fail.

## Layout

| Path | Purpose |
|---|---|
| `app/models.py` | SQLAlchemy models |
| `app/auth.py` | Clerk JWT verification / dev auth, user provisioning |
| `app/deps.py` | Organization & workspace authorization |
| `app/db.py` | Engine, sessions, RLS tenant context |
| `app/routers/` | HTTP endpoints |
| `app/deadlines/engine.py` | Deterministic deadline computation |
| `app/workers/` | Celery app and tasks |
| `alembic/` | Migrations (incl. RLS policies) |
| `scripts/export_openapi.py` | Writes the OpenAPI spec for the TS client |
