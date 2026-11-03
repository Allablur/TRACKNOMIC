"use client";
import { useResource, metric } from "@/lib/api";
import type { Overview, Genre, Release } from "@/lib/types";
import { PageHeading } from "@/components/layout/page-heading";
import { CatalogueCharts } from "@/components/charts/catalogue-charts";
import {
  FilterBar,
  Notice,
  DataState,
  panel,
  query,
  useFilters,
} from "./shared";
export function OverviewView({ genreOnly = false }: { genreOnly?: boolean }) {
  const [filters, setFilters] = useFilters();
  const params = query(filters);
  const overview = useResource<Overview>(`/dashboard/overview?${params}`);
  const genres = useResource<{ items: Genre[] }>(`/analytics/genres?${params}`);
  const releases = useResource<{ items: Release[] }>(
    `/analytics/releases?${params}`,
  );
  const retry = () => {
    overview.retry();
    genres.retry();
    releases.retry();
  };
  const loading = overview.loading || genres.loading || releases.loading;
  const error = overview.error || genres.error || releases.error;
  return (
    <>
      <PageHeading
        title={genreOnly ? "Genre analytics" : "Catalogue overview"}
        description="Explore the artists, releases, and recordings in your tracked catalogue."
      />
      <Notice />
      <FilterBar onApply={setFilters} />
      <DataState loading={loading} error={error} retry={retry} />
      {!loading && !error && overview.data && (
        <>
          <div className="mb-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {[
              ["Tracked artists", overview.data.artists],
              ["Release editions", overview.data.albums],
              ["Unique recordings", overview.data.tracks],
              ["Audience metrics", null],
            ].map(([label, value]) => (
              <article className={panel} key={label}>
                <p className="text-xs text-muted-foreground">{label}</p>
                <p className="mt-3 text-3xl font-semibold">
                  {metric(value as number | null)}
                </p>
                <p className="mt-2 text-xs text-muted-foreground">
                  {value === null
                    ? "See artist profiles for supported values"
                    : "Within selected filters"}
                </p>
              </article>
            ))}
          </div>
          {overview.data.demo_included && (
            <p className="mb-5 text-sm font-medium text-amber-800">
              This view includes fictional demo records.
            </p>
          )}
          <CatalogueCharts
            genres={genres.data?.items || []}
            releases={releases.data?.items || []}
          />
        </>
      )}
    </>
  );
}
