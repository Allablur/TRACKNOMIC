"""Server-only Spotify catalog access using Client Credentials (no user playback scopes)."""

import math
import re
import threading
import time
from urllib.parse import urlsplit

import httpx

from app.providers.musicbrainz import ProviderError

ID = re.compile(r"[A-Za-z0-9]{22}")


class SpotifyError(ProviderError):
    def __init__(self, message: str, status_code: int = 502, retry_after: int | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.retry_after = retry_after


def artist_identifier(value: str) -> str:
    value = value.strip()
    if value.startswith("spotify:artist:"):
        value = value.removeprefix("spotify:artist:")
    elif value.startswith("https://"):
        url = urlsplit(value)
        parts = url.path.strip("/").split("/")
        if parts and parts[0].startswith("intl-"):
            parts = parts[1:]
        if url.netloc != "open.spotify.com" or len(parts) != 2 or parts[0] != "artist":
            raise ValueError("Use a Spotify artist ID, URI, or open.spotify.com artist link")
        value = parts[1]
    if not ID.fullmatch(value):
        raise ValueError("A Spotify artist ID must contain 22 letters or digits")
    return value


def integer(value, maximum: int | None = None):
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        if maximum is None or value <= maximum:
            return value
    return None


class Spotify:
    token_url = "https://accounts.spotify.com/api/token"
    api_url = "https://api.spotify.com/v1"

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        market="ZA",
        max_albums=5,
        max_tracks=50,
        transport=None,
    ):
        if not client_id or not client_secret:
            raise SpotifyError("Configure Spotify client credentials on the API server", 503)
        self._client_id, self._client_secret = client_id, client_secret
        self.market = market
        self.max_albums = min(max(max_albums, 1), 20)
        self.max_tracks = min(max(max_tracks, 1), 200)
        self.transport = transport
        self._token = ""
        self._expires = 0.0
        self._blocked_until = 0.0
        self._lock = threading.Lock()

    def _send(self, method: str, url: str, **kwargs):
        try:
            with httpx.Client(
                timeout=15, follow_redirects=False, transport=self.transport
            ) as client:
                return client.request(method, url, **kwargs)
        except httpx.HTTPError:
            raise SpotifyError("Spotify could not be reached; retry later") from None

    @staticmethod
    def _data(response) -> dict:
        try:
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError
            return data
        except ValueError:
            raise SpotifyError("Spotify returned an invalid response") from None

    def _rate_limit(self, response):
        if response.status_code == 429:
            try:
                seconds = float(response.headers.get("Retry-After", "60"))
                delay = max(1, math.ceil(seconds)) if math.isfinite(seconds) else 60
            except ValueError:
                delay = 60
            self._blocked_until = time.monotonic() + delay
            raise SpotifyError("Spotify rate limit reached; wait before retrying", 429, delay)

    @staticmethod
    def _timeout(deadline):
        remaining = 15 if deadline is None else deadline - time.monotonic()
        if remaining <= 0:
            raise SpotifyError("Spotify import exceeded its time budget; reduce import limits")
        return min(15, remaining)

    def _access_token(self, refresh=False, deadline=None) -> str:
        with self._lock:
            remaining = self._blocked_until - time.monotonic()
            if remaining > 0:
                raise SpotifyError("Spotify rate limit is still active", 429, math.ceil(remaining))
            if self._token and time.monotonic() < self._expires and not refresh:
                return self._token
            response = self._send(
                "POST",
                self.token_url,
                auth=httpx.BasicAuth(self._client_id, self._client_secret),
                data={"grant_type": "client_credentials"},
                timeout=self._timeout(deadline),
            )
            self._rate_limit(response)
            if response.status_code in (400, 401, 403):
                raise SpotifyError(
                    "Spotify rejected the server credentials; check the Developer app", 503
                )
            if response.status_code != 200:
                raise SpotifyError("Spotify authorization is temporarily unavailable")
            data = self._data(response)
            token, expires = data.get("access_token"), integer(data.get("expires_in"))
            if not isinstance(token, str) or not token or not expires:
                raise SpotifyError("Spotify returned an invalid authorization response")
            self._token = token
            # Keep a safety margin, including for short-lived tokens.
            self._expires = time.monotonic() + max(0, expires - min(60, expires / 10))
            return token

    def _get(self, path: str, deadline: float, **params) -> dict:
        # Paths are constructed locally from validated IDs; never follow an upstream next URL.
        token = self._access_token(deadline=deadline)
        refreshed = False
        for attempt in range(3):
            if time.monotonic() >= deadline:
                raise SpotifyError(
                    "Spotify import exceeded its time budget; reduce album/track limits"
                )
            response = self._send(
                "GET",
                self.api_url + path,
                params=params,
                headers={"Authorization": f"Bearer {token}"},
                timeout=self._timeout(deadline),
            )
            self._rate_limit(response)
            if response.status_code == 401 and not refreshed:
                token = self._access_token(refresh=True, deadline=deadline)
                refreshed = True
                continue
            if response.status_code == 403:
                raise SpotifyError(
                    "Spotify denied this endpoint; check app mode and API access", 403
                )
            if response.status_code == 404:
                raise SpotifyError(
                    "Artist or release is unavailable in Spotify for this app/market", 404
                )
            if response.status_code >= 500 and attempt < 2:
                time.sleep(0.5 * (attempt + 1))
                continue
            if response.status_code != 200:
                raise SpotifyError("Spotify request failed; check the app access and try again")
            return self._data(response)
        raise SpotifyError("Spotify request retry limit reached")

    def _pages(self, path: str, cap: int, deadline: float, **params) -> list[dict]:
        items, offset = [], 0
        while len(items) < cap:
            # Ten works with restricted Development Mode pagination limits.
            limit = min(10, cap - len(items))
            page = self._get(
                path, deadline, market=self.market, limit=limit, offset=offset, **params
            )
            batch = page.get("items")
            if (
                not isinstance(batch, list)
                or len(batch) > limit
                or any(not isinstance(x, dict) for x in batch)
            ):
                raise SpotifyError("Spotify returned invalid catalogue pagination")
            items.extend(batch)
            offset += len(batch)
            if not batch or not page.get("next"):
                break
        return items

    def fetch_artist(self, identifier: str) -> dict:
        identifier = artist_identifier(identifier)
        deadline = time.monotonic() + 45
        artist = self._get(f"/artists/{identifier}", deadline)
        if artist.get("id") != identifier or not isinstance(artist.get("name"), str):
            raise SpotifyError("Spotify returned invalid artist metadata")
        albums, seen = [], set()
        for release in self._pages(
            f"/artists/{identifier}/albums",
            self.max_albums,
            deadline,
            include_groups="album,single",
        ):
            album_id = release.get("id", "")
            if not isinstance(album_id, str) or not ID.fullmatch(album_id):
                raise SpotifyError("Spotify returned an invalid album identifier")
            if album_id in seen:
                continue
            seen.add(album_id)
            tracks = []
            for position, track in enumerate(
                self._pages(f"/albums/{album_id}/tracks", self.max_tracks, deadline), 1
            ):
                track_id = track.get("id", "")
                if not isinstance(track_id, str) or not ID.fullmatch(track_id):
                    raise SpotifyError("Spotify returned an unavailable track; no import was saved")
                tracks.append(
                    {
                        "id": track_id,
                        "title": track["name"],
                        "duration_ms": integer(track.get("duration_ms")),
                        "disc_number": integer(track.get("disc_number")) or 1,
                        "position": integer(track.get("track_number")) or position,
                    }
                )
            albums.append(
                {
                    "id": album_id,
                    "title": release["name"],
                    "release_date": release.get("release_date"),
                    "release_type": release.get("album_type"),
                    "tracks": tracks,
                }
            )
        followers = artist.get("followers")
        return {
            "id": identifier,
            "name": artist["name"],
            "country": None,
            "type": None,
            "genres": [g for g in artist.get("genres", []) if isinstance(g, str)],
            "albums": albums,
            "metrics": {
                "followers": integer(followers.get("total"))
                if isinstance(followers, dict)
                else None,
                "popularity": integer(artist.get("popularity"), 100),
            },
        }

    def fetch_discography_step(
        self, identifier: str, checkpoint: dict | None, release_types: list[str]
    ):
        """One bounded HTTP page, no catalogue/track cap. State contains no credentials."""
        import copy
        import hashlib
        import json

        identifier = artist_identifier(identifier)
        state = copy.deepcopy(checkpoint) if checkpoint else {}
        deadline = time.monotonic() + 45
        if not state:
            artist = self._get(f"/artists/{identifier}", deadline)
            if artist.get("id") != identifier or not isinstance(artist.get("name"), str):
                raise SpotifyError("Spotify returned invalid artist metadata")
            genres = artist.get("genres") or []
            if not isinstance(genres, list):
                raise SpotifyError("Spotify returned invalid genre metadata")
            followers = artist.get("followers")
            payload = {
                "id": identifier,
                "name": artist["name"],
                "country": None,
                "type": None,
                "genres": [g for g in genres if isinstance(g, str)],
                "metrics": {
                    "followers": integer(followers.get("total"))
                    if isinstance(followers, dict)
                    else None,
                    "popularity": integer(artist.get("popularity"), 100),
                },
            }
            state = {
                "phase": "releases",
                "artist": {k: v for k, v in payload.items() if k != "metrics"},
                "market": self.market,
                "release_types": list(release_types),
                "release_offset": 0,
                "pending_releases": [],
                "seen_releases": [],
                "releases_imported": 0,
                "tracks_imported": 0,
                "track_offset": 0,
                "track_positions": [],
            }
            return {"payload": payload, "checkpoint": state, "complete": False, "finalize": None}
        if state.get("phase") == "done":
            return {"payload": None, "checkpoint": state, "complete": True, "finalize": None}
        market = state["market"]
        if state["phase"] == "releases":
            page = self._get(
                f"/artists/{identifier}/albums",
                deadline,
                market=market,
                include_groups=",".join(state["release_types"]),
                limit=10,
                offset=state["release_offset"],
            )
            rows = self._discography_rows(page)
            if page.get("next") and not rows:
                raise SpotifyError(
                    "Spotify release pagination did not advance; import is incomplete"
                )
            page_key = hashlib.sha256(
                json.dumps([row.get("id") for row in rows]).encode()
            ).hexdigest()
            if page.get("next") and page_key == state.get("last_release_page"):
                raise SpotifyError("Spotify repeated a release page; import is incomplete")
            seen = set(state["seen_releases"])
            releases = []
            for release in rows:
                id = release.get("id", "")
                if (
                    not isinstance(id, str)
                    or not ID.fullmatch(id)
                    or not isinstance(release.get("name"), str)
                ):
                    raise SpotifyError("Spotify returned invalid release metadata")
                if id in seen:
                    continue
                seen.add(id)
                releases.append(
                    {
                        "id": id,
                        "title": release["name"],
                        "release_date": release.get("release_date"),
                        "release_type": release.get("album_type"),
                    }
                )
            state.update(
                release_offset=state["release_offset"] + len(rows),
                pending_releases=releases,
                seen_releases=sorted(seen),
                more_releases=bool(page.get("next")),
                last_release_page=page_key,
            )
            state["phase"] = "tracks" if releases else "releases" if page.get("next") else "done"
            return {
                "payload": None,
                "checkpoint": state,
                "complete": state["phase"] == "done",
                "finalize": None,
            }
        if state["phase"] != "tracks" or not state["pending_releases"]:
            raise SpotifyError("Saved import state is invalid; contact the operator")
        release = state["pending_releases"][0]
        page = self._get(
            f"/albums/{release['id']}/tracks",
            deadline,
            market=market,
            limit=10,
            offset=state["track_offset"],
        )
        rows = self._discography_rows(page)
        if page.get("next") and not rows:
            raise SpotifyError("Spotify track pagination did not advance; import is incomplete")
        positions = set(state.get("track_positions", []))
        tracks = []
        for offset, track in enumerate(rows, state["track_offset"] + 1):
            id = track.get("id", "")
            if (
                not isinstance(id, str)
                or not ID.fullmatch(id)
                or not isinstance(track.get("name"), str)
            ):
                raise SpotifyError(
                    "Spotify returned an unavailable track; this import remains incomplete"
                )
            disc, position = (
                integer(track.get("disc_number")) or 1,
                integer(track.get("track_number")) or offset,
            )
            key = f"{disc}:{position}"
            if key in positions:
                raise SpotifyError(
                    "Spotify repeated track positions; this import remains incomplete"
                )
            positions.add(key)
            tracks.append(
                {
                    "id": id,
                    "title": track["name"],
                    "duration_ms": integer(track.get("duration_ms")),
                    "disc_number": disc,
                    "position": position,
                }
            )
        state["tracks_imported"] += len(tracks)
        state["track_offset"] += len(rows)
        state["track_positions"] = sorted(positions)
        payload = {**state["artist"], "albums": [{**release, "tracks": tracks}]}
        finalize = None
        if not page.get("next"):
            finalize = {"id": release["id"], "positions": sorted(positions)}
            state["releases_imported"] += 1
            state["pending_releases"] = state["pending_releases"][1:]
            state["track_positions"], state["track_offset"] = [], 0
            if not state["pending_releases"]:
                state["phase"] = "releases" if state["more_releases"] else "done"
        return {
            "payload": payload,
            "checkpoint": state,
            "complete": state["phase"] == "done",
            "finalize": finalize,
        }

    @staticmethod
    def _discography_rows(page):
        rows = page.get("items")
        if (
            not isinstance(rows, list)
            or len(rows) > 10
            or any(not isinstance(row, dict) for row in rows)
        ):
            raise SpotifyError("Spotify returned invalid catalogue pagination")
        return rows
