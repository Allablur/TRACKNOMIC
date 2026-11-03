import { PageHeading } from "@/components/layout/page-heading";
export default function Page() {
  return (
    <>
      <PageHeading
        title="Workspace settings"
        description="Data sources and the limits behind your catalogue."
      />
      <section className="space-y-6 rounded-xl border border-border bg-white p-6">
        <div>
          <h2 className="font-semibold">
            MusicBrainz · Primary metadata provider
          </h2>
          <p className="mt-2 text-sm text-muted-foreground">
            Attributed artist metadata, tags, official release editions, and
            recordings. Imports are bounded and require server-side
            authorization and an identifying User-Agent.
          </p>
        </div>
        <div>
          <h2 className="font-semibold">Demo catalogue · Fictional</h2>
          <p className="mt-2 text-sm text-muted-foreground">
            Explicitly loaded sample records for exploring the application
            without credentials. These are not real artists or real-world
            measurements.
          </p>
        </div>
        <div>
          <h2 className="font-semibold">Spotify · Not connected</h2>
          <p className="mt-2 text-sm text-muted-foreground">
            Optional supplementary integration for a later release. No Spotify
            metrics are assumed available.
          </p>
        </div>
        <div>
          <h2 className="font-semibold">Server configuration</h2>
          <p className="mt-2 text-sm text-muted-foreground">
            Manage database settings, ingestion authorization and data-source
            identity through secure server environment variables. Credentials
            are never managed in this browser.
          </p>
        </div>
      </section>
    </>
  );
}
