# Statistics calculated from imported data

Open **Artists**, choose an artist, and scroll to **Catalogue statistics**. Use **Refresh statistics** after an import, without making another Spotify request.

The API calculates these values from the saved catalogue, including releases already imported before this update. No database migration, new environment setting, credentials or paid data provider is required.

| Statistic | Calculation |
| --- | --- |
| Release editions | All saved releases linked to this artist, including appearances and editions |
| Albums | Release type `album`, case insensitive |
| Singles & EPs | Release type `single` or `ep`; Spotify classifies EPs under singles |
| Compilations | Release type `compilation` |
| Other / unknown | Remaining release types, including missing types |
| Distinct track IDs | Different saved track identities linked through these releases |
| Track positions | Every saved disc/position, including repeated tracks across releases |
| Known catalogue duration | Sum of non-null durations across distinct track IDs |
| Average known track duration | Average of those known durations; missing durations are excluded |
| Most recent dated release | Latest valid saved date; year/month-only dates sort from the start of that period, but display at the original precision |
| Releases by year | Valid dated editions grouped by year, with zeroes between the earliest and latest years |

The display includes duration coverage (known durations / distinct track IDs), excluded undated/invalid-date counts, a calculation timestamp and an accessible list behind the interactive yearly chart. Missing duration is **Unavailable**, while a supplied zero remains zero. A different ID can represent another version of the same song; distinct IDs do not guarantee distinct compositions. Guest-appearance releases may include other artists' tracks. Counts can be partial during failed/in-progress imports and describe saved catalogue coverage, not worldwide totals.

These calculations cannot produce monthly listeners, streams, country of origin or missing follower/popularity measurements. Those fields continue to use source data and explicit unavailable states.

Implementation: `GET /api/v1/artists/{artist_id}/catalogue-stats`, `backend/app/analytics/artist_stats.py`, `frontend/components/dashboard/artist-statistics.tsx`. SQL aggregates durations and track counts without loading each track into application memory; release metadata is read once for classification and valid partial-date handling. The new public read-only endpoint follows the existing artist access model.

Deployment: merge `feat/catalogue-statistics` into `main`, then deploy the API on Render and frontend on Vercel from that commit. Open an existing artist profile. No reimport is required to calculate from existing rows; reimport only when expanding or refreshing underlying source data.

Validation commands:

```bash
cd backend
uv run ruff check .
uv run ruff format --check .
uv run alembic check
uv run pytest -q
```

Use a disposable migrated PostgreSQL database for tests. Then seed its demo catalogue and start its API for browser fixtures. Never seed the deployed database for verification.

```bash
cd frontend
npm run lint
npm run typecheck
npm run format:check
npm test
NEXT_PUBLIC_DEFAULT_PROVIDER=demo npm run build
npm run test:e2e
```

Set `API_URL` to the local fixture API when needed. Restore the usual production build afterwards with `NEXT_PUBLIC_DEFAULT_PROVIDER` unset; production remains Spotify-first.
