# Import several Spotify artists from the website

The **Bulk import** screen lives at `/imports` and is linked from the sidebar and Workspace settings. It replaces repeated Swagger requests with a saved queue. No Spotify client secret is entered in the website.

## Deploy this update

1. Merge the bulk-import pull request into `main` after CI passes.
2. In Render, manually deploy the latest `main` commit. The existing startup script runs the new database migration before starting the API. Keep the working Spotify credentials, `INGESTION_ENABLED=true` and your private `INGESTION_TOKEN` in Render.
3. Redeploy the Vercel frontend from the same commit. Keep `API_URL` pointing to your API; do not add Spotify secrets or the ingestion token to Vercel.
4. No additional Render service or external queue is required. The API starts its background worker when ingestion is enabled. `BULK_WORKER_ENABLED` defaults to true; set it false only for maintenance. Optional `BULK_POLL_SECONDS` defaults to 2 seconds.

If the website reports that bulk imports are unavailable, confirm that Render and Vercel both run this update and that the migration succeeded. The old single-artist endpoint remains available.

## Start your batch

A ready-to-upload CSV with the two artist links supplied for your first batch is available at [examples/spotify-import.csv](examples/spotify-import.csv). It contains links only; those artists have not been queued/imported automatically.

1. Open your Trackonomics website and click **Bulk import**.
2. Paste the **value of `INGESTION_TOKEN`** from Render into the password field and click **Unlock imports**. Use only the token, without a Bearer prefix. This is not your Spotify client secret. The app retains it only in memory for the current page session; it is not written to local/session storage, cookies or the queue database.
3. Paste one artist link, artist URI or 22-character artist ID per line. You can paste share links with their `?si=...` query; the app normalizes them to artist IDs.
4. Alternatively, choose a CSV/text file. A one-column file needs no header. Multi-column CSV should include `artist_id`, `spotify_id`, `spotify_artist_id`, `spotify_url`, `artist_url`, `url` or `link`. Other columns are ignored. Example structure:

```csv
name,spotify_url
Artist of your choice,PASTE_THE_ARTIST_SHARE_LINK_HERE
```

Replace the placeholder with a genuine artist link before uploading. Files/pasted text are limited to 64 KB and 100 unique artists per batch. CSV quoting, BOM and CRLF are supported. Invalid rows are reported before submission; fix them before starting. Duplicates within the submitted list are removed even if they use different link/URI formats. Separate intentional batches may reimport an existing artist, updating the same canonical Spotify record.

5. Click **Start import**. The server saves the normalized artist IDs and returns a batch ID. An idempotency key prevents a repeated submission after an ambiguous network error from creating the same batch twice.
6. Follow the per-artist statuses: **Queued**, **Importing**, **Imported**, **Failed** or **Cancelled**. Artist names appear when real metadata is imported; unknown names are not invented. **View artist** opens successful imports in your catalogue.

## Timing and background behavior

Imports run one at a time. The existing 60-second per-provider cooldown applies across both manual and bulk Spotify imports. Spotify's Retry-After can require a longer wait, and that backoff is saved in PostgreSQL so all workers/manual imports respect it. The screen shows the next eligible attempt time; it is not a guarantee of completion at that instant.

The queue survives a page refresh or API restart. On free hosting, processing can pause while the API is asleep/down; it resumes when the service is awake. A claimed item interrupted by a crash becomes eligible for recovery after its two-minute lease expires. Existing source-ID upserts prevent duplicate artist/release/track records if interrupted work must be retried. This is at-least-once recovery, not an exactly-once external-request guarantee.

Only the opaque batch ID is saved in browser local storage. After refreshing or reopening the site, enter your operator token again to reconnect. Copy the batch ID for use on another device; enter it in **Reconnect to a batch** after unlocking. Never put the token into the batch ID field or share it in screenshots.

## Controls

- **Pause queue:** no new artists are started; an in-flight request can finish.
- **Resume queue:** continue pending artists while respecting cooldowns.
- **Cancel remaining:** cancel unstarted work. Already imported data is not deleted. An in-flight request can still finish; use **Refresh progress** to see its final result.
- **Retry failed artists:** requeue only failed entries, preserving successful ones. Attempt counts restart for the new retry cycle; ingestion audit runs retain historical attempts.
- **Lock screen:** forget the in-memory token without cancelling the server queue.
- **Create another batch:** available after completion/cancellation. Active/paused batches are capped at ten per API database.

A Spotify access/configuration error pauses the batch after the affected artist instead of failing every remaining artist. Correct Render settings and redeploy if needed, then retry/resume. Rate limits defer work automatically; five repeated provider rate-limit attempts pause the remaining batch for operator review. A missing/unavailable individual artist fails that entry while other artists continue.

The screen never stores Spotify app credentials. It submits normalized IDs, not the uploaded file or unrelated CSV columns. All queue/status/control endpoints require the existing Bearer operator token; this remains a shared-operator application, not a multi-user account system.

## API and implementation

Protected endpoints under `/api/v1/ingestion/spotify/batches`:

- `GET /access`: validate operator access and configured worker/client-credential presence; does not claim live Spotify authorization was verified.
- `POST /`: create a batch with `request_id` (UUID), `artist_ids` (1–100 values), optional `name`; returns 202. Reusing the request ID with different input returns 409.
- `GET /{batch_id}`: saved progress, counts, errors and timing.
- `POST /{batch_id}/pause`, `/resume`, `/cancel`, `/retry`: control work.

The migration adds batch/item tables, a nullable ingestion-run retry timestamp and cooldown indexes. Worker claims use PostgreSQL advisory locks plus row locks/leases; multiple API processes cannot import queue items simultaneously. Individual imports share the original provider lock, transactional upserts and audit handling. Batch creation has a short advisory transaction lock, an active-batch cap and an idempotent request UUID. Control/finalization locks serialize cancellation and completion updates. Queue records never contain authorization tokens.

The browser suite uses mocked protected queue responses, and a separate local test runs the real API/background worker against disposable PostgreSQL with only the upstream Spotify provider mocked. No deployed database, Spotify quota or real operator token is used in those tests.
