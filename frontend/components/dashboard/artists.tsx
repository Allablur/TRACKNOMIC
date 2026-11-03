"use client";
import Link from "next/link";
import { SourceLinks } from "./source-links";
import { useState } from "react";
import { useResource, metric } from "@/lib/api";
import type { Artist, Page } from "@/lib/types";
import { PageHeading } from "@/components/layout/page-heading";
import { Button } from "@/components/ui/button";
import {
  FilterBar,
  Notice,
  DataState,
  Pagination,
  panel,
  query,
  useFilters,
} from "./shared";
export function ComparisonTable({ items }: { items: Artist[] }) {
  return (
    <section className={`${panel} mt-6 overflow-x-auto`}>
      <h2 className="mb-4 font-semibold">Artist comparison</h2>
      <table className="w-full text-left text-sm">
        <caption className="mb-4 text-left text-xs text-muted-foreground">
          Counts cover tracked catalogue entries. Audience metrics include a
          source and capture time when supplied.
        </caption>
        <thead>
          <tr>
            <th className="p-3">Metric</th>
            {items.map((a) => (
              <th key={a.id} className="p-3">
                {a.name}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {(
            [
              ["Release editions", "album_count"],
              ["Track positions", "track_count"],
              ["Followers", "followers"],
              ["Popularity", "popularity"],
            ] as const
          ).map(([label, key]) => (
            <tr key={key} className="border-t border-border">
              <th className="p-3">{label}</th>
              {items.map((a) => (
                <td key={a.id} className="p-3">
                  {metric(a[key])}
                </td>
              ))}
            </tr>
          ))}
          <tr className="border-t border-border">
            <th className="p-3">Metric source / capture</th>
            {items.map((a) => (
              <td key={a.id} className="p-3">
                {a.metrics_provider || "Unavailable"}
                {a.metrics_captured_at ? ` / ${a.metrics_captured_at}` : ""}
              </td>
            ))}
          </tr>
        </tbody>
      </table>
    </section>
  );
}
export function ArtistsView({ compare = false }: { compare?: boolean }) {
  const [filters, setFilters] = useFilters();
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<string[]>([]);
  const [ids, setIds] = useState("");
  const artists = useResource<Page<Artist>>(
    `/artists/search?${query(filters)}&limit=20&offset=${offset}`,
  );
  const comparison = useResource<{ items: Artist[] }>(
    ids ? `/artists/compare?ids=${ids}` : null,
  );
  return (
    <>
      <PageHeading
        title={compare ? "Compare artists" : "Artist intelligence"}
        description={
          compare
            ? "Select two to five artists and compare supported catalogue and audience metrics."
            : "Search attributed artist metadata and explore release histories."
        }
      />
      <Notice />
      <FilterBar
        onApply={(value) => {
          setFilters(value);
          setOffset(0);
        }}
      />
      {compare && (
        <div className="mb-5 flex items-center gap-4">
          <Button
            disabled={selected.length < 2}
            onClick={() => {
              setIds(selected.join(","));
              comparison.retry();
            }}
          >
            Compare selected ({selected.length}/5)
          </Button>
          <Button
            variant="outline"
            onClick={() => {
              setSelected([]);
              setIds("");
            }}
          >
            Clear selection
          </Button>
        </div>
      )}
      <DataState {...artists} empty={artists.data?.total === 0} />
      {artists.data && !artists.error && artists.data.total > 0 && (
        <>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {artists.data.items.map((artist) => (
              <article key={artist.id} className={panel}>
                {compare && (
                  <label className="mb-3 flex items-center gap-2 text-xs">
                    <input
                      type="checkbox"
                      aria-label={`Select ${artist.name}`}
                      checked={selected.includes(artist.id)}
                      disabled={
                        selected.length === 5 && !selected.includes(artist.id)
                      }
                      onChange={(e) =>
                        setSelected(
                          e.target.checked
                            ? [...selected, artist.id]
                            : selected.filter((id) => id !== artist.id),
                        )
                      }
                    />
                    Include in comparison
                  </label>
                )}
                <div className="mb-4 flex h-11 w-11 items-center justify-center rounded-full bg-primary/10 text-lg font-semibold text-primary">
                  {artist.name.charAt(0)}
                </div>
                <h2 className="font-semibold">
                  <Link
                    className="hover:underline"
                    href={`/artists/${artist.id}`}
                  >
                    {artist.name}
                  </Link>
                </h2>
                <p className="mt-1 text-xs text-muted-foreground">
                  {artist.country || "Country unavailable"} ·{" "}
                  {artist.type || "Type unavailable"}
                </p>
                <p className="mt-3 text-sm">
                  {artist.genres.join(" · ") || "No genre tags"}
                </p>
                <dl className="mt-5 grid grid-cols-2 gap-3 text-xs">
                  <div>
                    <dt className="text-muted-foreground">Releases</dt>
                    <dd className="mt-1 text-lg font-semibold">
                      {artist.album_count}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-muted-foreground">Followers</dt>
                    <dd className="mt-1 font-semibold">
                      {metric(artist.followers)}
                    </dd>
                  </div>
                </dl>
                <p className="mt-4 border-t border-border pt-3 text-xs text-muted-foreground">
                  Source: <SourceLinks sources={artist.sources} />
                </p>
              </article>
            ))}
          </div>
          <Pagination
            offset={offset}
            total={artists.data.total}
            onChange={setOffset}
          />
        </>
      )}
      {ids && (
        <>
          <DataState {...comparison} />
          {comparison.data && <ComparisonTable items={comparison.data.items} />}
        </>
      )}
    </>
  );
}
