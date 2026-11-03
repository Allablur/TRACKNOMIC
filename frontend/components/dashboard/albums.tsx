"use client";
import Link from "next/link";
import { SourceLinks } from "./source-links";
import { useState } from "react";
import { useResource } from "@/lib/api";
import type { Album, Page } from "@/lib/types";
import { PageHeading } from "@/components/layout/page-heading";
import {
  FilterBar,
  Notice,
  DataState,
  Pagination,
  panel,
  query,
  useFilters,
} from "./shared";
export function AlbumTable({ items }: { items: Album[] }) {
  return (
    <div className={`${panel} overflow-x-auto`}>
      <table className="w-full text-left text-sm">
        <caption className="mb-4 text-left text-xs text-muted-foreground">
          Release editions; partial dates retain source precision.
        </caption>
        <thead>
          <tr>
            {["Release", "Artist", "Date", "Type", "Tracks", "Source"].map(
              (h) => (
                <th key={h} className="p-3">
                  {h}
                </th>
              ),
            )}
          </tr>
        </thead>
        <tbody>
          {items.map((a) => (
            <tr key={a.id} className="border-t border-border">
              <th className="p-3 font-medium">{a.title}</th>
              <td className="p-3">
                {a.artists.map((artist) => (
                  <Link
                    key={artist.id}
                    href={`/artists/${artist.id}`}
                    className="mr-2 text-primary hover:underline"
                  >
                    {artist.name}
                  </Link>
                ))}
              </td>
              <td className="p-3 whitespace-nowrap">
                {a.release_date || "Unavailable"}
              </td>
              <td className="p-3">{a.release_type || "Unavailable"}</td>
              <td className="p-3">{a.track_count}</td>
              <td className="p-3">
                <SourceLinks sources={a.sources} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
export function AlbumsView() {
  const [filters, setFilters] = useFilters();
  const [offset, setOffset] = useState(0);
  const data = useResource<Page<Album>>(
    `/albums?${query(filters)}&limit=20&offset=${offset}`,
  );
  return (
    <>
      <PageHeading
        title="Album intelligence"
        description="Release dates, catalogue structure, and track counts with source attribution."
      />
      <Notice />
      <FilterBar
        onApply={(value) => {
          setFilters(value);
          setOffset(0);
        }}
      />
      <DataState {...data} empty={data.data?.total === 0} />
      {data.data && data.data.total > 0 && (
        <>
          <AlbumTable items={data.data.items} />
          <Pagination
            offset={offset}
            total={data.data.total}
            onChange={setOffset}
          />
        </>
      )}
    </>
  );
}
