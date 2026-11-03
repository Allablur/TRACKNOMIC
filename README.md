# Trackonomics

A music catalogue analytics platform built with Next.js, FastAPI and PostgreSQL. Explore attributed artist metadata, compare catalogue sizes, inspect release activity and export filtered CSV/PDF reports.

> The bundled demo is entirely fictional. Charts describe the tracked catalogue, not global music popularity. Missing followers, popularity and growth metrics are never invented.

![Trackonomics demo dashboard](docs/images/dashboard.png)

## What works

- Responsive overview with artist/release/recording counts and interactive Recharts visualizations.
- Paginated artist search and source/country/name filters; artist profiles and discographies.
- Comparison of two to five artists with explicit unavailable-metric states.
- Album edition lists, partial source dates, genre representation and release-year trends.
- Filtered CSV/PDF reports with source attribution, report limits and formula-safe CSV fields.
- Bounded, operator-authorized MusicBrainz ingestion with paced requests, retries, transactional upserts and run auditing.
- PostgreSQL migrations, test suites, security controls, CI and Vercel/Render configuration.

Spotify integration is optional and not connected. No user accounts or tenant-private data access are implemented. Hosting configuration is prepared; a live deployment has not been created.

## Local development

Requires Node 24 (see `frontend/.nvmrc`), Python 3.12+, uv (tested with 0.12.23), Docker Engine and Compose v2. Use the existing checkout; cloud tasks are already isolated and do not need a worktree.

From the repository root, copy templates **only if those local files do not exist**:

```sh
cp -n .env.example .env
cp -n backend/.env.example backend/.env
cp -n frontend/.env.example frontend/.env.local
docker compose up -d --wait db
cd backend
uv sync --locked
uv run alembic upgrade head
uv run python -m app.seed
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

In another terminal, from the repository root:

```sh
cd frontend
npm ci
npm run dev
```

The frontend uses port 3000; API docs are on port 8000 at `/docs`. Open `/dashboard` in the frontend. `GET /health` must return HTTP 200 and `{"status":"ok","database":"connected"}`. `python scripts/smoke.py` validates readiness, workspace routes and the frontend API proxy.

The root `.env` configures Compose. `backend/.env` configures FastAPI. `frontend/.env.local` configures the server-side upstream. Keep PostgreSQL credentials/port and `DATABASE_URL` in sync. Local credentials are development defaults; replace them before deployment. Never commit `.env` files. PostgreSQL initializes credentials only on a new data volume.

`uv run python -m app.seed` explicitly loads demo records and is safe to repeat. It adds no followers or popularity. Omit it for an empty catalogue. Stop the DB with `docker compose stop db`; `docker compose down` retains data, while `docker compose down -v` permanently deletes it.

## Checks

With PostgreSQL migrated, from `backend/`:

```sh
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run alembic check
```

From `frontend/`:

```sh
npm run lint
npm run typecheck
npm run format:check
npm test
npm run build
npm run test:e2e
```

Browser tests require the demo seed and running API on port 8000. They start a production frontend on port 3100. Install a browser with `npx playwright install --with-deps chromium` if needed; this cloud environment uses `/usr/bin/chromium`. Set `CHROMIUM_PATH` for another system binary. The checks assert the deterministic demo counts, so use a dedicated development/test database rather than a mixed real catalogue. Unit-only backend checks without PostgreSQL: `uv run pytest -m 'not integration'`.

For production-mode local startup use `npm start` after building the frontend, and `bash scripts/start-production.sh` from backend (migrates first). Stop only your own existing frontend/API processes before reusing their ports.

## API and ingestion

Read endpoints under `/api/v1`: dashboard overview; artist search, profile, albums and comparison; albums; genre/release analytics. `POST /api/v1/reports` accepts `format` (`csv` or `pdf`), `provider` (`all`, `demo`, `musicbrainz`), `q` (artist name), and `country`. OpenAPI documents all parameters.

Live ingestion is disabled by default. To enable it, securely set `INGESTION_ENABLED=true`, `INGESTION_TOKEN` (32+ random characters), and an identifying `MUSICBRAINZ_USER_AGENT` with your contact/project URL. Call `POST /api/v1/ingestion/artists` with a Bearer token and `{"artist_mbid":"ARTIST-UUID"}`. Do not paste tokens into source files, browsers or chat. Configure egress to `musicbrainz.org` if restricted. Imports are bounded to 20 official release editions by default (maximum 100), paced at least 1.05 seconds per request, globally serialized and limited to one new run per minute. Live external-provider access was not validated in this cloud instance; provider behavior is covered by deterministic mocked tests.

## Documentation and deployment

- [Phase-by-phase implementation, files, commands and results](docs/phase-log.md)
- [Architecture and interview talking points](docs/architecture.md)
- [Security and performance boundaries](docs/security.md)
- [Vercel + Render deployment runbook](docs/deployment.md)

`render.yaml`, `frontend/vercel.json` and `.github/workflows/ci.yml` prepare deployment and validation. Review hosting plans and secure settings before using them. No deployment or GitHub Actions run is claimed until performed remotely.
