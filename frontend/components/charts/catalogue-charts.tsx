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
import type { Genre, Release } from "@/lib/types";
import { panel } from "@/components/dashboard/shared";
export function CatalogueCharts({
  genres,
  releases,
}: {
  genres: Genre[];
  releases: Release[];
}) {
  return (
    <div className="grid gap-6 xl:grid-cols-2">
      <section className={panel}>
        <h2 className="mb-1 font-semibold">Genre representation</h2>
        <p className="mb-6 text-xs text-muted-foreground">
          Artists may appear in more than one genre.
        </p>
        {genres.length ? (
          <div
            className="h-72"
            role="img"
            aria-label="Bar chart of artists by genre"
          >
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={genres}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="genre" tick={{ fontSize: 11 }} />
                <YAxis allowDecimals={false} />
                <Tooltip />
                <Bar dataKey="artists" fill="#125e52" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <p>No genre data available.</p>
        )}
        <details className="mt-3 text-xs">
          <summary>View genre data</summary>
          <ul>
            {genres.map((g) => (
              <li key={g.genre}>
                {g.genre}: {g.artists} artists
              </li>
            ))}
          </ul>
        </details>
      </section>
      <section className={panel}>
        <h2 className="mb-1 font-semibold">Release activity</h2>
        <p className="mb-6 text-xs text-muted-foreground">
          Release editions with known dates. Missing years show zero.
        </p>
        {releases.length ? (
          <div
            className="h-72"
            role="img"
            aria-label="Bar chart of releases by year"
          >
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={releases}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="year" tick={{ fontSize: 11 }} />
                <YAxis allowDecimals={false} />
                <Tooltip />
                <Bar dataKey="releases" fill="#c89c50" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <p>No dated releases available.</p>
        )}
        <details className="mt-3 text-xs">
          <summary>View release data</summary>
          <ul>
            {releases.map((y) => (
              <li key={y.year}>
                {y.year}: {y.releases} releases
              </li>
            ))}
          </ul>
        </details>
      </section>
    </div>
  );
}
