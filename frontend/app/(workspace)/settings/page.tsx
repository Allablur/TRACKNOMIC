import Link from "next/link";
import { PageHeading } from "@/components/layout/page-heading";
export default function Page() {
  return (
    <>
      <PageHeading
        title="Workspace settings"
        description="Real metadata from Spotify, with source attribution and explicit availability."
      />
      <p className="mb-6">
        <Link href="/imports" className="font-medium text-primary underline">
          Open bulk import →
        </Link>
      </p>
      <section className="space-y-6 rounded-xl border border-border bg-white p-6">
        <div>
          <h2 className="font-semibold">Spotify · Default catalogue source</h2>
          <p className="mt-2 text-sm text-muted-foreground">
            Import real artist names, album and single releases, track metadata,
            and available genre tags using your Spotify Developer app. Supported
            fields depend on app access and market. Follower and popularity
            values are shown only when actually supplied.
          </p>
        </div>
        <div>
          <h2 className="font-semibold">Connect your Spotify Developer app</h2>
          <ol className="mt-3 list-decimal space-y-2 pl-5 text-sm leading-6 text-muted-foreground">
            <li>
              Create an app in the{" "}
              <a
                className="text-primary underline"
                href="https://developer.spotify.com/dashboard"
                target="_blank"
                rel="noopener noreferrer"
              >
                Spotify Developer Dashboard
              </a>{" "}
              and select Web API.
            </li>
            <li>
              Set SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET in the API host’s
              secure environment settings. Set INGESTION_ENABLED=true and a
              strong INGESTION_TOKEN.
            </li>
            <li>
              Redeploy the API. In its /docs page, authorize with your ingestion
              token and use POST /api/v1/ingestion/spotify/artists with a
              Spotify artist share link.
            </li>
            <li>
              Refresh the catalogue. Repeat imports update existing Spotify
              records; requests are rate-limited.
            </li>
          </ol>
          <p className="mt-3 text-xs text-muted-foreground">
            Client credentials stay on the API server. This page does not reveal
            whether a particular deployment has configured them. See
            docs/spotify.md in the repository for complete setup and
            troubleshooting.
          </p>
        </div>
        <div>
          <h2 className="font-semibold">Market and import scope</h2>
          <p className="mt-2 text-sm text-muted-foreground">
            The default market is ZA. On Bulk import, choose albums,
            singles/EPs, compilations or guest appearances. New batches page
            through every available release and track in the selected groups,
            saving progress between pages. Catalogue counts depend on Spotify
            access and market, and are not streaming totals. The older
            single-request API remains a limited snapshot; use the website for
            full-discography imports.
          </p>
        </div>
        <div>
          <h2 className="font-semibold">MusicBrainz · Additional source</h2>
          <p className="mt-2 text-sm text-muted-foreground">
            Existing MusicBrainz metadata remains available through the source
            filter. Providers retain separate identifiers; duplicate real-world
            artists are not automatically merged across providers.
          </p>
        </div>
        <div>
          <h2 className="font-semibold">No automatic sample data</h2>
          <p className="mt-2 text-sm text-muted-foreground">
            The normal workspace shows Spotify records and starts empty until
            real imports succeed. Existing fictional records are excluded by
            default. CI uses isolated, explicitly labelled test fixtures; there
            is no synthetic fallback for failed imports.
          </p>
        </div>
      </section>
    </>
  );
}
