# Phase 1 architecture

- `frontend/`: Next.js App Router, TypeScript, Tailwind CSS v4, shadcn/ui-compatible component configuration and Button.
- `backend/`: FastAPI, Pydantic Settings, synchronous SQLAlchemy with Psycopg, Alembic, pytest and Ruff.
- `docker-compose.yml`: PostgreSQL 17, loopback-only port binding and a persistent named volume.
- `sample-data/`: reserved for clearly identified demo data.

`GET /health` runs `SELECT 1` on PostgreSQL and returns HTTP 200 with `{"status":"ok","database":"connected"}`. Database failures return HTTP 503 with a generic message. `/docs` exposes the generated API documentation.

Phase 1 establishes infrastructure only. Database domain tables and migrations start in Phase 3; no `create_all` or automatic schema creation is used. MusicBrainz ingestion, optional Spotify, analytics, charts, reports and authentication are later phases. No API credentials are required yet.

MusicBrainz is the planned primary metadata provider. Metrics must remain nullable and unavailable when absent; catalogue representation is not global popularity.
