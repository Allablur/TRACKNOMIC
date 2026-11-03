import type { Source } from "@/lib/types";
export function SourceLinks({ sources }: { sources: Source[] }) {
  return (
    <>
      {sources.length
        ? sources.map((source, index) => (
            <span key={`${source.provider}:${source.external_id}`}>
              {index > 0 ? ", " : ""}
              {source.provider === "spotify" &&
              source.url?.startsWith("https://open.spotify.com/") ? (
                <a
                  href={source.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-primary underline underline-offset-2"
                >
                  Spotify ↗
                </a>
              ) : source.provider === "demo" ? (
                "Fictional test fixture"
              ) : (
                source.provider
              )}
            </span>
          ))
        : "Unattributed"}
    </>
  );
}
