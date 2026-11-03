from functools import lru_cache

from app.core.config import get_settings
from app.providers.spotify import Spotify, SpotifyError
from app.services.import_control import import_slot
from app.services.ingestion import ingest


@lru_cache(maxsize=1)
def get_spotify() -> Spotify:
    settings = get_settings()
    return Spotify(
        settings.spotify_client_id,
        settings.spotify_client_secret.get_secret_value(),
        settings.spotify_market,
        settings.spotify_max_albums,
        settings.spotify_max_tracks_per_album,
    )


def perform_spotify_import(db, identifier, provider):
    try:
        with import_slot(db, "spotify"):
            artist = ingest(db, lambda: provider.fetch_artist(identifier), "spotify")
        settings = get_settings()
        return {
            "id": str(artist.id),
            "name": artist.name,
            "provider": "spotify",
            "spotify_url": f"https://open.spotify.com/artist/{identifier}",
            "import_scope": {
                "market": settings.spotify_market,
                "max_albums": settings.spotify_max_albums,
                "max_tracks_per_album": settings.spotify_max_tracks_per_album,
            },
        }
    except (KeyError, ValueError, TypeError):
        raise SpotifyError(
            "Spotify returned unusable metadata; no catalogue changes were saved"
        ) from None
