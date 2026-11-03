"use client";
import { useState } from "react";
import { DEFAULT_PROVIDER } from "@/lib/catalogue";
import type { Filters } from "@/lib/types";
import { Button } from "@/components/ui/button";
export const panel = "rounded-xl border border-border bg-white p-6 shadow-sm";
export const field =
  "rounded-lg border border-border bg-white px-3 py-2 text-sm focus-visible:outline-2 focus-visible:outline-primary";
export function useFilters() {
  return useState<Filters>({ provider: DEFAULT_PROVIDER, q: "", country: "" });
}
export function query(filters: Filters) {
  return new URLSearchParams(filters).toString();
}
export function FilterBar({
  onApply,
}: {
  onApply: (filters: Filters) => void;
}) {
  return (
    <form
      aria-label="Catalogue filters"
      className="mb-6 flex flex-wrap items-end gap-3"
      onSubmit={(event) => {
        event.preventDefault();
        const data = new FormData(event.currentTarget);
        onApply({
          provider: String(data.get("provider")),
          q: String(data.get("q") || ""),
          country: String(data.get("country") || ""),
        });
      }}
    >
      <label className="grid gap-2 text-xs font-medium">
        Search artist
        <input
          name="q"
          placeholder="Artist name…"
          maxLength={150}
          className={field}
        />
      </label>
      <label className="grid gap-2 text-xs font-medium">
        Source
        <select
          name="provider"
          defaultValue={DEFAULT_PROVIDER}
          className={field}
        >
          <option value="spotify">Spotify</option>
          <option value="live">All live sources</option>
          {DEFAULT_PROVIDER === "demo" && (
            <option value="demo">Fictional test fixtures</option>
          )}
          <option value="musicbrainz">MusicBrainz</option>
        </select>
      </label>
      <label className="grid gap-2 text-xs font-medium">
        Country
        <input
          name="country"
          placeholder="e.g. ZA"
          maxLength={3}
          className={`${field} w-24`}
        />
      </label>
      <Button type="submit">Apply filters</Button>
    </form>
  );
}
export function Notice() {
  return (
    <p className="mb-6 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-xs leading-5 text-amber-900">
      Charts describe imported catalogue entries, not streaming totals or global
      popularity. Imports are bounded and depend on source access and market.
      Missing audience metrics remain unavailable.
    </p>
  );
}
export function DataState({
  loading,
  error,
  retry,
  empty = false,
}: {
  loading: boolean;
  error?: string;
  retry: () => void;
  empty?: boolean;
}) {
  if (error)
    return (
      <div role="alert" className={panel}>
        <p>{error}</p>
        <Button className="mt-3" onClick={retry}>
          Retry
        </Button>
      </div>
    );
  if (loading)
    return (
      <p role="status" className={panel}>
        Loading catalogue…
      </p>
    );
  if (empty)
    return (
      <div className={panel}>
        <h2 className="font-semibold">No matching records</h2>
        <p className="mt-2 text-sm text-muted-foreground">
          Try another filter, or import a real Spotify artist through the
          authorized API. See Workspace settings for setup instructions.
        </p>
      </div>
    );
  return null;
}
export function Pagination({
  offset,
  total,
  onChange,
}: {
  offset: number;
  total: number;
  onChange: (offset: number) => void;
}) {
  return (
    <div className="mt-5 flex items-center justify-between gap-3 text-sm">
      <span>
        {total === 0
          ? "0 records"
          : `${offset + 1}–${Math.min(offset + 20, total)} of ${total}`}
      </span>
      <div className="flex gap-2">
        <Button
          variant="outline"
          disabled={offset === 0}
          onClick={() => onChange(Math.max(0, offset - 20))}
        >
          Previous
        </Button>
        <Button
          variant="outline"
          disabled={offset + 20 >= total}
          onClick={() => onChange(offset + 20)}
        >
          Next
        </Button>
      </div>
    </div>
  );
}
