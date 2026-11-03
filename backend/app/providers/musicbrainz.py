"""A bounded MusicBrainz client. Requests are paced, including retries."""

import threading
import time
from uuid import UUID

import httpx

_lock = threading.Lock()


class ProviderError(Exception):
    pass


class MusicBrainz:
    base_url = "https://musicbrainz.org/ws/2"

    def __init__(self, user_agent: str, max_releases: int = 20, transport=None):
        if not user_agent.strip():
            raise ValueError(
                "An identifying MUSICBRAINZ_USER_AGENT with contact information is required"
            )
        self.user_agent = user_agent
        self.max_releases = min(max(max_releases, 1), 100)
        self.transport = transport

    def get(self, path: str, **params) -> dict:
        for attempt in range(3):
            with _lock:
                time.sleep(1.05)
                try:
                    with httpx.Client(timeout=20, transport=self.transport) as client:
                        response = client.get(
                            self.base_url + path,
                            params={**params, "fmt": "json"},
                            headers={"User-Agent": self.user_agent, "Accept": "application/json"},
                        )
                except httpx.HTTPError as exc:
                    raise ProviderError("MusicBrainz network request failed") from exc
            if response.status_code in (429, 503) and attempt < 2:
                # Respect a bounded Retry-After; otherwise exponential backoff.
                retry = response.headers.get("Retry-After", "")
                time.sleep(min(float(retry), 60) if retry.isdigit() else 2**attempt)
                continue
            try:
                response.raise_for_status()
                return response.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise ProviderError("MusicBrainz returned an unusable response") from exc
        raise ProviderError("MusicBrainz retry limit reached")

    def fetch_artist(self, mbid: UUID) -> dict:
        artist = self.get(f"/artist/{mbid}", inc="tags")
        listing = self.get("/release", artist=str(mbid), status="official", limit=self.max_releases)
        releases = []
        for item in listing.get("releases", []):
            release = self.get(f"/release/{UUID(item['id'])}", inc="recordings+release-groups")
            tracks = []
            for disc_index, medium in enumerate(release.get("media", []), 1):
                for position, track in enumerate(medium.get("tracks", []), 1):
                    recording = track.get("recording", {})
                    tracks.append(
                        {
                            "id": recording.get("id", track["id"]),
                            "title": recording.get("title", track.get("title", "Untitled")),
                            "duration_ms": track.get("length"),
                            "disc_number": medium.get("position", disc_index),
                            "position": track.get("position", position),
                        }
                    )
            releases.append(
                {
                    "id": release["id"],
                    "title": release["title"],
                    "release_date": release.get("date"),
                    "release_type": release.get("release-group", {}).get("primary-type"),
                    "tracks": tracks,
                }
            )
        return {
            "id": artist["id"],
            "name": artist["name"],
            "country": artist.get("country"),
            "type": artist.get("type"),
            "disambiguation": artist.get("disambiguation"),
            "genres": [tag["name"] for tag in artist.get("tags", [])[:20]],
            "albums": releases,
        }
