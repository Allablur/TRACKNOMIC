// Production defaults to real Spotify data. Only CI/local fixture builds opt into demo.
export const DEFAULT_PROVIDER =
  process.env.NEXT_PUBLIC_DEFAULT_PROVIDER === "demo" ? "demo" : "spotify";
