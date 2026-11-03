import { describe, it, expect } from "vitest";
import { parseArtists, spotifyArtistId } from "@/lib/bulk-import";
const first = "A".repeat(22),
  second = "B".repeat(22);
describe("bulk import parsing", () => {
  it("normalizes artist links, share queries, URIs and IDs before deduplication", () => {
    const result = parseArtists(
      `${first}\nspotify:artist:${first}\nhttps://open.spotify.com/artist/${second}?si=share`,
    );
    expect(result).toEqual({ ids: [first, second], duplicates: 1, errors: [] });
  });
  it("accepts the supplied artist share link without its tracking query", () => {
    expect(
      spotifyArtistId(
        "https://open.spotify.com/artist/3tVQdUvClmAT7URs9V3rsp?si=1TPkjcw5Tu2pde-d005Rcw",
      ),
    ).toBe("3tVQdUvClmAT7URs9V3rsp");
  });
  it("accepts multi-column quoted CSV and Windows newlines", () => {
    const result = parseArtists(
      `name,spotify_url\r\n"Artist, One","https://open.spotify.com/artist/${first}"\r\n"Artist Two",spotify:artist:${second}\r\n`,
    );
    expect(result.ids).toEqual([first, second]);
    expect(result.errors).toEqual([]);
  });
  it("accepts a BOM, headers and internationalized share paths", () => {
    expect(
      parseArtists(
        `\uFEFFartist_id\nhttps://open.spotify.com/intl-en/artist/${first}\n`,
      ).ids,
    ).toEqual([first]);
  });
  it("rejects album links, arbitrary hosts and userinfo host spoofing", () => {
    for (const value of [
      `https://open.spotify.com/album/${first}`,
      `https://evil.example/artist/${first}`,
      `https://user@open.spotify.com/artist/${first}`,
      "not-an-id",
    ]) {
      expect(spotifyArtistId(value)).toBeNull();
      expect(parseArtists(value).errors).toHaveLength(1);
    }
  });
  it("reports invalid rows instead of silently dropping them", () => {
    const result = parseArtists(`${first}\ninvalid\n${second}`);
    expect(result.ids).toEqual([first, second]);
    expect(result.errors[0]).toContain("Row 2");
  });
  it("requires a header for ambiguous multi-column files", () => {
    expect(parseArtists(`Artist Name,${first}`).errors[0]).toContain(
      "needs an artist_id or spotify_url header",
    );
  });
  it("rejects malformed CSV quoting", () => {
    expect(parseArtists('"unclosed').errors).toHaveLength(1);
    expect(parseArtists('"closed"invalid').errors).toHaveLength(1);
  });
  it("bounds unique artist counts and file sizes", () => {
    const rows = Array.from({ length: 101 }, (_, i) =>
      String(i).padStart(22, "0"),
    ).join("\n");
    expect(parseArtists(rows).errors[0]).toContain("100 unique");
    expect(parseArtists("x".repeat(65537)).errors[0]).toContain("64 KB");
  });
  it("does not echo potentially sensitive invalid input into errors", () => {
    expect(
      parseArtists("accidentally-pasted-private-token").errors.join(),
    ).not.toContain("accidentally-pasted-private-token");
  });
});
