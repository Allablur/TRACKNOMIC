export const MAX_ARTISTS = 100;
export const MAX_FILE_BYTES = 64 * 1024;
const artistId = /^[A-Za-z0-9]{22}$/;
export function spotifyArtistId(input: string): string | null {
  let value = input.trim();
  if (value.startsWith("spotify:artist:"))
    value = value.slice("spotify:artist:".length);
  else if (value.startsWith("https://")) {
    try {
      const url = new URL(value);
      let parts = url.pathname.split("/").filter(Boolean);
      if (parts[0]?.startsWith("intl-")) parts = parts.slice(1);
      if (
        url.hostname !== "open.spotify.com" ||
        url.username ||
        url.password ||
        parts.length !== 2 ||
        parts[0] !== "artist"
      )
        return null;
      value = parts[1];
    } catch {
      return null;
    }
  }
  return artistId.test(value) ? value : null;
}
function csvRows(text: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [],
    cell = "",
    quoted = false,
    closed = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (quoted) {
      if (ch === '"') {
        if (text[i + 1] === '"') {
          cell += '"';
          i++;
        } else {
          quoted = false;
          closed = true;
        }
      } else cell += ch;
      continue;
    }
    if (ch === '"') {
      if (cell.trim() || closed)
        throw new Error(
          "Malformed CSV quotation. Use one link per line or a valid CSV file.",
        );
      quoted = true;
    } else if (ch === ",") {
      row.push(cell.trim());
      cell = "";
      closed = false;
    } else if (ch === "\n" || ch === "\r") {
      if (ch === "\r" && text[i + 1] === "\n") i++;
      row.push(cell.trim());
      if (row.some(Boolean)) rows.push(row);
      row = [];
      cell = "";
      closed = false;
    } else if (closed && !/\s/.test(ch))
      throw new Error("Unexpected text after a CSV quotation.");
    else cell += ch;
  }
  if (quoted) throw new Error("A CSV quotation was not closed.");
  row.push(cell.trim());
  if (row.some(Boolean)) rows.push(row);
  return rows;
}
export function parseArtists(text: string): {
  ids: string[];
  duplicates: number;
  errors: string[];
} {
  if (new TextEncoder().encode(text).length > MAX_FILE_BYTES)
    return {
      ids: [],
      duplicates: 0,
      errors: ["Use a file or pasted list smaller than 64 KB."],
    };
  try {
    const rows = csvRows(text.replace(/^\uFEFF/, ""));
    if (!rows.length) return { ids: [], duplicates: 0, errors: [] };
    const headers = [
      "artist_id",
      "spotify_id",
      "spotify_artist_id",
      "spotify_url",
      "artist_url",
      "url",
      "link",
    ];
    const column = rows[0].findIndex((cell) =>
      headers.includes(cell.toLowerCase().replace(/[ -]/g, "_")),
    );
    const data = column >= 0 ? rows.slice(1) : rows;
    const ids: string[] = [];
    const seen = new Set<string>();
    const errors: string[] = [];
    let duplicates = 0;
    data.forEach((row, index) => {
      const line = index + (column >= 0 ? 2 : 1);
      if (column < 0 && row.length > 1) {
        errors.push(
          `Row ${line}: multi-column CSV needs an artist_id or spotify_url header.`,
        );
        return;
      }
      const id = spotifyArtistId(row[column >= 0 ? column : 0] || "");
      if (!id) {
        errors.push(
          `Row ${line}: use a Spotify artist link, artist URI, or 22-character artist ID.`,
        );
        return;
      }
      if (seen.has(id)) {
        duplicates++;
        return;
      }
      seen.add(id);
      ids.push(id);
    });
    if (ids.length > MAX_ARTISTS)
      errors.push(`Use at most ${MAX_ARTISTS} unique artists per batch.`);
    return { ids, duplicates, errors };
  } catch (error) {
    return {
      ids: [],
      duplicates: 0,
      errors: [
        error instanceof Error
          ? error.message
          : "Unable to read this artist list.",
      ],
    };
  }
}
export type ImportStatus =
  "pending" | "running" | "succeeded" | "failed" | "cancelled";
export type BulkItem = {
  id: string;
  spotify_id: string;
  position: number;
  status: ImportStatus;
  attempts: number;
  name: string | null;
  artist_id: string | null;
  error: string | null;
  available_at: string;
  last_http_status: number | null;
};
export type BulkBatch = {
  id: string;
  name: string;
  status: "active" | "paused" | "cancelled" | "completed";
  server_time: string;
  next_attempt_at: string | null;
  worker_enabled: boolean;
  total: number;
  counts: Record<ImportStatus, number>;
  items: BulkItem[];
};
export class ImportApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}
export async function importRequest<T>(
  path: string,
  token: string,
  options: { method?: string; body?: unknown; signal?: AbortSignal } = {},
): Promise<T> {
  const response = await fetch(`/api/v1/ingestion/spotify/batches${path}`, {
    method: options.method || "GET",
    headers: {
      Authorization: `Bearer ${token}`,
      ...(options.body ? { "Content-Type": "application/json" } : {}),
    },
    body: options.body ? JSON.stringify(options.body) : undefined,
    signal: options.signal,
    cache: "no-store",
  });
  const data = await response
    .json()
    .catch(() => ({ detail: "The API returned an unreadable response." }));
  if (!response.ok)
    throw new ImportApiError(
      response.status,
      typeof data.detail === "string"
        ? data.detail
        : `Request failed (HTTP ${response.status}). Check the input and API settings.`,
    );
  return data as T;
}
