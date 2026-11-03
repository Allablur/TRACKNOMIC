# Trackonomics

Music industry analytics built on attributed artist and release metadata.

Phase 1 provides a Next.js frontend, FastAPI backend and PostgreSQL development database. It does not yet ingest music data or provide analytics.

## Prerequisites

- Node.js 22+ and npm
- Python 3.12+ and [uv](https://docs.astral.sh/uv/)
- Docker Engine and Docker Compose v2

## Local setup

From the repository root:

```sh
cp .env.example .env
cp backend/.env.example backend/.env
docker compose up -d --wait db
cd backend
uv sync --locked
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

In another terminal, from the repository root:

```sh
cd frontend
npm ci
npm run dev
```

Frontend: port 3000. API docs: port 8000 at `/docs`. Check readiness with `curl --fail http://127.0.0.1:8000/health`; it must return `{"status":"ok","database":"connected"}`.

The example credentials are local-only defaults. If changing PostgreSQL credentials or port in the root `.env`, update `DATABASE_URL` in `backend/.env` to match. PostgreSQL initializes credentials only when its data volume is first created. Never use these defaults in production or commit `.env` files. CORS origins are a JSON array configured in `backend/.env`.

## Validation

With PostgreSQL running, from `backend/`:

```sh
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run alembic current
```

Without a database, run only the unit checks with `uv run pytest -m 'not integration'`. The integration test is a real database-backed readiness request and must pass to accept Phase 1.

From `frontend/`:

```sh
npm run lint
npm run typecheck
npm run format:check
npm run build
npm start
```

Request the production frontend on port 3000 and confirm the Trackonomics landing page renders. `npm run format` and `uv run ruff format .` apply formatting.

Stop the database with `docker compose stop db`; `docker compose down` removes containers while retaining data. `docker compose down -v` permanently deletes local database data.

Alembic is configured but contains no domain revisions yet. See [architecture](docs/architecture.md) for scope and later phases. shadcn/ui aliases and theme are configured in `frontend/components.json`; the initial Button lives in `frontend/components/ui/`.
