# Connect real Spotify catalogue data

The production workspace now defaults to Spotify. There is no automatic fictional fallback. Existing demo records are retained but excluded from default reads and reports; **All live sources** includes only Spotify and MusicBrainz. No existing records are deleted by this change.

The integration imports real artist metadata, available genre tags, albums/singles, and track metadata. It uses server-to-server **Client Credentials**, so there is no visitor Spotify login, user-library access, playback or audio download. Endpoint access depends on Spotify's current app mode, account requirements, market, quotas and developer terms. Do not assume follower or popularity fields are provided. Unsupported/missing values stay null; actual zeros stay zero. Country and artist type are not inferred from your market.

## 1. Create your Spotify Developer app

1. Open https://developer.spotify.com/dashboard and sign in with your Spotify account.
2. Choose **Create app**. Name it Trackonomics and describe your catalogue metadata use. Select **Web API** when asked which APIs you will use.
3. Follow Spotify's current account/Premium and Development Mode requirements shown in the dashboard. Creating credentials does not guarantee every endpoint is permitted.
4. Supply your actual website/project URL if requested. This integration does not use redirect-based login. If the dashboard nevertheless requires a redirect URI, an explicit loopback URI such as `http://127.0.0.1:8888/callback` can be registered for development; Trackonomics does not implement that callback or use it for Client Credentials.
5. Review and accept the applicable developer terms. Before a public/commercial release, confirm that your metadata retention, attribution, reporting and analytics use complies with Spotify's current terms; this implementation does not confer extra rights to Spotify content.
6. Open the app's settings and locate **Client ID** and **Client Secret**. Keep the secret private; do not paste it into GitHub, a public environment variable, browser application code, screenshots or chat.

## 2. Merge the integration and configure Render

Merge the Spotify integration pull request into `main` once CI passes. In Render, open **trackonomics-api → Environment** and add these settings:

| Variable | Value |
| --- | --- |
| `SPOTIFY_CLIENT_ID` | Client ID from your Developer app |
| `SPOTIFY_CLIENT_SECRET` | Client Secret, entered securely in Render |
| `SPOTIFY_MARKET` | `ZA`, or another two-letter uppercase market you intend to use |
| `SPOTIFY_MAX_ALBUMS` | `5` (legacy single-request endpoint only) |
| `SPOTIFY_MAX_TRACKS_PER_ALBUM` | `50` (legacy single-request endpoint only) |
| `INGESTION_ENABLED` | `true` |
| `INGESTION_TOKEN` | A separate random operator token of at least 32 characters |

Generate the operator token on a trusted computer with `python -c "import secrets; print(secrets.token_urlsafe(48))"` and store it securely. **It is not your Spotify client secret or Spotify access token.** The operator token protects this application's write API; Spotify credentials authorize server-to-server Spotify requests.

Keep the existing `DATABASE_URL` database binding. MusicBrainz's User-Agent is required only when invoking the MusicBrainz importer, not for Spotify. Add the actual API hostname to trusted hosts when using a custom domain; Render's own external hostname is detected automatically.

Save the environment settings and explicitly deploy the latest merged commit (automatic deployment is disabled in the blueprint). Open `/health` on the API and require HTTP 200. Restart/redeploy after credential rotation: access tokens are cached in process memory, not in PostgreSQL or the browser.

## 3. Configure Vercel

Keep `API_URL` pointing to your actual Render HTTPS API base URL, with no trailing slash. Redeploy the frontend from the merged integration commit. **Do not set `NEXT_PUBLIC_DEFAULT_PROVIDER=demo` on Vercel**; omit it to use Spotify. Never add Spotify credentials or the ingestion token to Vercel's public variables. Until an import succeeds, the catalogue will correctly show zero artists and an empty state.

## 4. Import your first real artist

For multiple artists, use **Bulk import** in the website: unlock with your operator token, paste links or upload a CSV, choose **Albums**, **Singles & EPs**, optional **Compilations** / **Guest appearances**, and start the saved queue. This website flow imports all available pages and resumes saved progress after interruptions. It does not use the five-album/fifty-track limits. Requeue an existing artist to expand an earlier limited import. See [bulk-import.md](bulk-import.md). No Swagger JSON is needed. The single-artist alternative follows below.

1. Open the artist in Spotify. Use **Share → Copy link to artist**. Use an artist link, not an album, playlist or track link.
2. Open `https://YOUR-API-HOST/docs` in a trusted browser.
3. Choose **Authorize**, enter the **INGESTION_TOKEN** you configured in Render, and authorize the Bearer scheme. Enter the token itself if the UI already supplies the Bearer prefix.
4. Expand **POST /api/v1/ingestion/spotify/artists**, choose **Try it out**, and send:

```json
{"artist_id": "PASTE_YOUR_SPOTIFY_ARTIST_LINK_HERE"}
```

The same field accepts a 22-character artist ID or `spotify:artist:...` URI. No client secret belongs in the request body.

5. Execute. HTTP **201** returns the internal artist ID, the Spotify source link and the configured market/album/track limits.
6. Refresh the frontend Artists and Dashboard pages. Their default source is Spotify. Click source links to view the original artist/release on Spotify.
7. Wait at least 60 seconds before another import. Repeat imports update records with the same Spotify identifiers and append dated availability/metric snapshots. No cross-provider artist merging occurs automatically.

For an alternative that requires only Python on your computer, run from the repository root:

```sh
python scripts/import_spotify.py \
  --api https://YOUR-API-HOST \
  --artist 'YOUR_SPOTIFY_ARTIST_LINK'
```

The helper prompts privately for your operator token, enforces HTTPS except for loopback development and refuses redirects rather than forwarding that token to another destination. It contacts your deployed API, not your PostgreSQL database; no external database access rule or service shell is needed.

## 5. Understand the imported scope

The legacy single-request endpoint defaults fetch up to five album/single entries and fifty track positions per release in the chosen market. These are bounded catalogue counts, not total Spotify streams, listeners, complete discographies or global popularity. Raise limits cautiously (maximum 20 albums and 200 positions per album); the importer has a time budget and aborts without saving partial catalogue updates if it cannot finish. Pagination uses locally constructed Spotify endpoints, never arbitrary upstream pagination URLs. No artwork/audio is downloaded or rehosted.

Spotify access tokens are cached until shortly before expiry. A 401 refreshes authorization once; transient server failures have bounded retries. A 429 is returned with Spotify's Retry-After without sleeping through long cooldowns or inventing replacement data. Single-request failures roll back that request’s changes; full website imports retain earlier committed pages and retry their saved checkpoint. Failed ingestion runs are preserved, and the global lock/cooldown still protects the service.

## Troubleshooting

| Response | Meaning / action |
| --- | --- |
| 401 | Your Trackonomics ingestion token is missing or incorrect. Use the Render `INGESTION_TOKEN`, not the Spotify secret. |
| 403 | Spotify denied the requested endpoint. Check current Developer app mode, account requirements and access. |
| 404 | The artist/release is unavailable for this app/market, or the artist ID is wrong. |
| 422 | Use a Spotify artist ID/URI/share link and valid request fields. |
| 429 | Wait the returned Retry-After; another import or the local 60-second cooldown can also apply. |
| 503 | Ingestion is disabled, Spotify credentials are missing, or Spotify rejected the configured credentials. Check Render settings and redeploy. |
| 502 | Spotify returned unusable data, a network/server error persisted, or the time budget was exceeded. Existing catalogue records are retained; reduce import limits if needed. |

The cloud development environment also needs allowed HTTPS destinations `accounts.spotify.com` and `api.spotify.com` for live requests. Render's runtime is configured separately. No live Spotify call can be verified until real credentials and outbound access are available. Tests use explicit synthetic responses only; they are not a production fallback.

## Developer validation

Run backend migrations and `uv run pytest` against a dedicated PostgreSQL database. Provider tests exercise OAuth, caching, 401 refresh, URL validation, pagination, null/zero metrics, denial/rate-limit responses, source links, API authorization/cooldown and rollback auditing with mocked Spotify responses.

The existing CI/browser fixture suite deliberately builds with `NEXT_PUBLIC_DEFAULT_PROVIDER=demo` and seeds an isolated test database. To run that suite locally, build with `NEXT_PUBLIC_DEFAULT_PROVIDER=demo npm run build` before `npm run test:e2e`. Rebuild without that variable afterwards to restore Spotify production defaults. The CI fixture setting is not part of Vercel deployment configuration.
