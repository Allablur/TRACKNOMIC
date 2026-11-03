export type Source = {
  provider: string;
  external_id: string;
  url?: string | null;
};
export type Artist = {
  id: string;
  name: string;
  country: string | null;
  type: string | null;
  disambiguation: string | null;
  genres: string[];
  album_count: number;
  track_count: number;
  followers: number | null;
  popularity: number | null;
  metrics_provider: string | null;
  metrics_captured_at: string | null;
  sources: Source[];
};
export type Album = {
  id: string;
  title: string;
  release_date: string | null;
  date_precision: string;
  release_type: string | null;
  track_count: number;
  artists: { id: string; name: string }[];
  sources: Source[];
};
export type Page<T> = {
  items: T[];
  total: number;
  limit: number;
  offset: number;
};
export type Overview = {
  artists: number;
  albums: number;
  tracks: number;
  provider: string;
  scope: string;
  demo_included: boolean;
  followers: null;
  popularity: null;
};
export type Genre = { genre: string; artists: number };
export type Release = { year: number; releases: number };
export type Filters = { provider: string; q: string; country: string };
