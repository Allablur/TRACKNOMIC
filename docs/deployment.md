# Vercel + Render deployment

This repository contains deployment configuration, not a live deployment. No hosting accounts, remote resources or DNS changes have been created. The user selected configuration preparation. Review current provider plans, limits and configuration schemas before deploying.

## Render: API and managed PostgreSQL

1. Push the reviewed repository to GitHub. In Render, create a Blueprint using root `render.yaml`.
2. Review the selected `free` plans. Free web services may sleep and free databases may expire; they are demonstration choices, not production durability. Choose paid service/database plans and backup retention for a persistent deployment. No resources or charges were created by this task.
3. The API build installs uv 0.12.23 and locked production dependencies. `backend/scripts/start-production.sh` migrates before starting Uvicorn using Render's `PORT`. API `/health` checks the real database. First boot has an empty catalogue; the UI defaults to Spotify rather than fictional records.
4. `DATABASE_URL` is supplied through the database binding, never committed. Both `postgres://` and `postgresql://` normalize to Psycopg. The platform-provided `RENDER_EXTERNAL_HOSTNAME` is added to trusted hosts. Add any custom hostname via `ALLOWED_HOSTS` as a JSON array. Use the database's TLS connection options for external connections; the app preserves URL query parameters.
5. Default CORS is empty in the blueprint because the frontend uses a same-origin server proxy. Add exact browser origins as a JSON array only if supporting direct browser-to-API access. Configure trusted ingress proxy IP ranges with `FORWARDED_ALLOW_IPS` if needed; do not blindly trust arbitrary forwarded headers.
6. Live ingestion is OFF. For Spotify, follow [spotify.md](spotify.md): configure `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET`, `INGESTION_ENABLED=true` and a random server-only `INGESTION_TOKEN` of at least 32 characters. Only MusicBrainz imports need an identifying `MUSICBRAINZ_USER_AGENT` with contact/project URL. Supply secrets only through Render's secret settings. Requests require a Bearer header. Never place this token in Vercel public variables or browser code. Allow outbound HTTPS to `musicbrainz.org` where egress restrictions apply.
7. Optional demo: run `uv run --no-dev python -m app.seed` from backend in a trusted shell after migrations. If the hosting root excludes `sample-data`, upload `sample-data/catalogue.json` through a trusted deployment artifact and use `--file /path/catalogue.json`. Seeding is explicit and idempotent; it never runs automatically in production. Do not import demo records into a private real catalogue accidentally.

The service uses one worker; locks and cooldown state are PostgreSQL-backed. Automatic deployment is disabled in the blueprint. Review and trigger deployments explicitly.

## Vercel: frontend

1. Import the same GitHub repository and select **frontend** as the project root. `frontend/vercel.json` selects Next.js, `npm ci`, and `npm run build`.
2. Use Node 24. Leave `NEXT_PUBLIC_DEFAULT_PROVIDER` unset (the `demo` value is only for isolated fixture builds). Set the server variable `API_URL` to the deployed Render HTTPS base URL, without a trailing slash. Do not use `NEXT_PUBLIC_` variables for backend credentials. `API_URL` contains no credential.
3. Build/deploy after setting the upstream. Next's rewrite sends `/api/*` to the API, including downloadable reports. Changing the upstream requires rebuilding/redeploying. Point previews to an appropriate staging API, not a production write-capable integration.
4. Check that the chosen plan's proxy duration covers bounded report generation. Do not expose ingestion to anonymous callers; it remains server-authorized even through the proxy.

## Release verification and operations

Run `python scripts/smoke.py --api https://YOUR-API-HOST --frontend https://YOUR-FRONTEND-HOST` after deployment. Use the actual hostnames; this task does not claim those requests were run against remote services. Then verify filtered search, two-artist comparison and CSV/PDF downloads in a browser. An empty initial database should show zeros/empty states, not invented metrics.

`.github/workflows/ci.yml` runs reversible migrations, backend tests/lint, frontend unit/type/lint/format/build checks and real Chromium tests with disposable PostgreSQL and seeded demo data. Local equivalents were executed; the remote GitHub Actions run remains unverified until pushed.

For release rollback, redeploy the previous Git revision. Review schema compatibility first; do not automatically downgrade a production database. Take managed database backups before schema releases and exercise restore in staging. Health 503 means database readiness failed; inspect provider logs using the request ID without copying credentials. Gate a production launch on TLS, backups, ingress rate limits/timeouts, monitoring and a tested recovery path. See `security.md` for scope and remaining operational controls.

## Bulk imports

After deploying the bulk-import migration/API and frontend, the website exposes `/imports`. The API lifespan starts a database-backed worker when INGESTION_ENABLED=true and BULK_WORKER_ENABLED=true (default). No extra service is provisioned. Keep existing server credentials/operator token private. Free-plan sleep can pause progress; saved batches resume when the API wakes. See bulk-import.md for controls, restart recovery and operator access.
