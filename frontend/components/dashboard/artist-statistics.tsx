"use client";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { useResource, metric } from "@/lib/api";
import type { ArtistCatalogueStats } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { DataState, panel } from "./shared";

function duration(milliseconds: number | null) {
  if (milliseconds === null) return "Unavailable";
  const seconds = Math.round(milliseconds / 1000);
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  return `${hours ? `${hours}h ` : ""}${minutes}m ${seconds % 60}s`;
}

export function ArtistStatistics({ id }: { id: string }) {
  const stats = useResource<ArtistCatalogueStats>(
    `/artists/${id}/catalogue-stats`,
  );
  return (
    <section
      aria-label="Imported catalogue statistics"
      className={`${panel} mb-6`}
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-xl font-semibold">Catalogue statistics</h2>
        <Button
          variant="outline"
          disabled={stats.loading}
          onClick={stats.retry}
        >
          Refresh statistics
        </Button>
      </div>
      <p className="mt-3 text-sm text-muted-foreground">
        Calculated from saved releases and tracks. Counts may be incomplete
        while an import is running. These figures do not measure listeners,
        plays or popularity.
      </p>
      <DataState {...stats} />
      {stats.data && (
        <>
          <dl className="mt-6 grid grid-cols-2 gap-6 lg:grid-cols-4">
            {[
              ["Release editions", metric(stats.data.release_count)],
              ["Albums", metric(stats.data.album_count)],
              ["Singles & EPs", metric(stats.data.single_ep_count)],
              ["Compilations", metric(stats.data.compilation_count)],
              [
                "Other / unknown releases",
                metric(stats.data.other_release_count),
              ],
              ["Distinct track IDs", metric(stats.data.distinct_track_count)],
              ["Track positions", metric(stats.data.track_position_count)],
              [
                "Known catalogue duration",
                duration(stats.data.known_duration_ms),
              ],
              [
                "Average known track duration",
                duration(stats.data.average_known_duration_ms),
              ],
            ].map(([label, value]) => (
              <div key={label}>
                <dt className="text-xs text-muted-foreground">{label}</dt>
                <dd className="mt-2 text-xl font-semibold">{value}</dd>
              </div>
            ))}
          </dl>
          <p className="mt-5 text-xs text-muted-foreground">
            Durations available for{" "}
            {metric(stats.data.known_duration_track_count)} of{" "}
            {metric(stats.data.distinct_track_count)} distinct track IDs.
            Repeated track IDs count once toward duration; different IDs can
            represent versions of the same song. Track positions include repeat
            appearances across releases. Guest-appearance releases can include
            other artists’ tracks.
          </p>
          <p className="mt-5 text-sm">
            <strong>Most recent dated release:</strong>{" "}
            {stats.data.latest_release
              ? `${stats.data.latest_release.title} · ${stats.data.latest_release.release_date} (${stats.data.latest_release.date_precision} precision)`
              : "Unavailable"}
          </p>
          <p className="mt-2 text-xs text-muted-foreground">
            Dates keep the source’s precision; partial dates sort from the start
            of their known year or month.
          </p>
          <h3 className="mt-6 font-semibold">Releases by year</h3>
          <p className="mt-2 text-xs text-muted-foreground">
            {stats.data.undated_release_count} releases without a valid date are
            excluded. Gaps show zero imported releases.
          </p>
          {stats.data.releases_by_year.length ? (
            <>
              <div
                className="mt-4 h-64"
                role="img"
                aria-label="Artist releases by year"
              >
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={stats.data.releases_by_year}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} />
                    <XAxis dataKey="year" tick={{ fontSize: 11 }} />
                    <YAxis allowDecimals={false} />
                    <Tooltip />
                    <Bar
                      dataKey="releases"
                      fill="#125e52"
                      radius={[4, 4, 0, 0]}
                    />
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <details className="mt-3 text-xs">
                <summary>View yearly release counts</summary>
                <ul>
                  {stats.data.releases_by_year.map((item) => (
                    <li key={item.year}>
                      {item.year}: {item.releases} releases
                    </li>
                  ))}
                </ul>
              </details>
            </>
          ) : (
            <p className="mt-3 text-sm">No dated releases available.</p>
          )}
          <p className="mt-5 text-xs text-muted-foreground">
            Calculated {new Date(stats.data.calculated_at).toLocaleString()}{" "}
            from the saved catalogue. Refresh after imports to update.
          </p>
        </>
      )}
    </section>
  );
}
