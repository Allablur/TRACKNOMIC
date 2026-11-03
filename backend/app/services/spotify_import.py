from datetime import UTC, datetime, timedelta
from functools import lru_cache

from sqlalchemy import delete, select, tuple_

from app.core.config import get_settings
from app.models import AlbumTrack, Artist, IngestionRun, SourceMapping
from app.providers.spotify import Spotify, SpotifyError
from app.services.import_control import import_slot
from app.services.ingestion import ingest, save_artist


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


def perform_discography_step(db, identifier, provider, checkpoint, release_types):
    """Leave page writes uncommitted: worker commits them with its checkpoint."""
    with import_slot(db, "spotify", continuation=bool(checkpoint)):
        run = IngestionRun(provider="spotify")
        db.add(run)
        db.commit()
        run_id = run.id
        try:
            step = provider.fetch_discography_step(identifier, checkpoint, release_types)
            payload = step["payload"]
            if checkpoint and payload is not None:
                mapping = db.scalar(
                    select(SourceMapping).where(
                        SourceMapping.entity_type == "artist",
                        SourceMapping.provider == "spotify",
                        SourceMapping.external_id == identifier,
                    )
                )
                current = db.get(Artist, mapping.entity_id) if mapping else None
                if current is None:
                    raise SpotifyError("Saved artist metadata was not found; start a new batch")
                # Do not overwrite fresher artist metadata while resuming older track pages.
                payload = {
                    **payload,
                    "name": current.name,
                    "country": current.country,
                    "type": current.type,
                    "disambiguation": current.disambiguation,
                    "genres": [genre.name for genre in current.genres],
                }
            if payload is not None:
                artist = save_artist(db, payload, "spotify", replace_tracks=False)
            else:
                mapping = db.scalar(
                    select(SourceMapping).where(
                        SourceMapping.entity_type == "artist",
                        SourceMapping.provider == "spotify",
                        SourceMapping.external_id == identifier,
                    )
                )
                artist = db.get(Artist, mapping.entity_id) if mapping else None
            if artist is None:
                raise SpotifyError(
                    "Saved artist metadata was not found; this import remains incomplete"
                )
            final = step.get("finalize")
            if final is not None:
                mapping = db.scalar(
                    select(SourceMapping).where(
                        SourceMapping.entity_type == "album",
                        SourceMapping.provider == "spotify",
                        SourceMapping.external_id == final["id"],
                    )
                )
                positions = [tuple(map(int, key.split(":"))) for key in final["positions"]]
                statement = delete(AlbumTrack).where(AlbumTrack.album_id == mapping.entity_id)
                if positions:
                    statement = statement.where(
                        tuple_(AlbumTrack.disc_number, AlbumTrack.position).not_in(positions)
                    )
                db.execute(statement)
            run.status, run.finished_at = "succeeded", datetime.now(UTC)
            db.flush()
            return {
                "id": str(artist.id),
                "name": artist.name,
                "complete": step["complete"],
                "checkpoint": step["checkpoint"],
            }
        except Exception as exc:
            db.rollback()
            failed = db.get(IngestionRun, run_id)
            failed.status, failed.finished_at = "failed", datetime.now(UTC)
            failed.error = "Discography page failed; prior committed pages are retained."
            retry = getattr(exc, "retry_after", None)
            if getattr(exc, "status_code", None) == 429 and isinstance(retry, int):
                failed.retry_after_at = datetime.now(UTC) + timedelta(seconds=max(1, retry))
            db.commit()
            if isinstance(exc, (KeyError, ValueError, TypeError)):
                raise SpotifyError(
                    "Spotify returned unusable metadata; retry this import page"
                ) from None
            raise
