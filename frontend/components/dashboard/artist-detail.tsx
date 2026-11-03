"use client";
import Link from "next/link";
import { SourceLinks } from "./source-links";
import { useResource, metric } from "@/lib/api";
import type { Artist, Album } from "@/lib/types";
import { PageHeading } from "@/components/layout/page-heading";
import { ArtistStatistics } from "./artist-statistics";
import { AlbumTable } from "./albums";
import { DataState, Notice, panel } from "./shared";
export function ArtistDetail({ id }: { id: string }) {
  const artist = useResource<Artist>(`/artists/${id}`);
  const albums = useResource<{ items: Album[] }>(`/artists/${id}/albums`);
  return (
    <>
      <Link
        href="/artists"
        className="mb-6 inline-block text-sm text-primary hover:underline"
      >
        ← All artists
      </Link>
      <DataState {...artist} />
      {artist.data && (
        <>
          <PageHeading
            title={artist.data.name}
            description={
              artist.data.disambiguation ||
              "Artist metadata and tracked releases."
            }
          />
          <Notice />
          <section className={`${panel} mb-6`}>
            <dl className="grid gap-5 sm:grid-cols-4">
              {[
                ["Country", artist.data.country || "Unavailable"],
                ["Genres", artist.data.genres.join(", ") || "Unavailable"],
                ["Followers", metric(artist.data.followers)],
                ["Popularity", metric(artist.data.popularity)],
              ].map(([label, value]) => (
                <div key={label}>
                  <dt className="text-xs text-muted-foreground">{label}</dt>
                  <dd className="mt-2 font-medium">{value}</dd>
                </div>
              ))}
            </dl>
            <p className="mt-5 text-xs text-muted-foreground">
              Sources: <SourceLinks sources={artist.data.sources} />. Metrics:{" "}
              {artist.data.metrics_provider || "Unavailable"}
              {artist.data.metrics_captured_at
                ? ` · captured ${artist.data.metrics_captured_at}`
                : ""}
              .
            </p>
          </section>
          <ArtistStatistics id={id} />
          <h2 className="mb-4 text-xl font-semibold">Discography</h2>
          <DataState {...albums} empty={albums.data?.items.length === 0} />
          {albums.data && albums.data.items.length > 0 && (
            <AlbumTable items={albums.data.items} />
          )}
        </>
      )}
    </>
  );
}
