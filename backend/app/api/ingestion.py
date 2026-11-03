import secrets
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.core.config import get_settings
from app.core.database import engine
from app.models import IngestionRun
from app.providers.musicbrainz import MusicBrainz, ProviderError
from app.providers.spotify import Spotify, SpotifyError, artist_identifier
from app.services.ingestion import ingest

router = APIRouter(prefix="/api/v1/ingestion", tags=["ingestion"])
bearer = HTTPBearer(auto_error=False)


def authorize(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]):
    settings = get_settings()
    if not settings.ingestion_enabled or not settings.ingestion_token:
        raise HTTPException(503, "Live ingestion is disabled")
    if credentials is None or not secrets.compare_digest(
        credentials.credentials.encode(), settings.ingestion_token.encode()
    ):
        raise HTTPException(
            401, "Valid ingestion authorization required", headers={"WWW-Authenticate": "Bearer"}
        )


class ImportRequest(BaseModel):
    artist_mbid: UUID


@contextmanager
def import_slot(db: Session, provider: str):
    # Separate connection holds the global lock across import commits and providers.
    with engine.connect() as lock:
        if not lock.scalar(text("SELECT pg_try_advisory_lock(824017)")):
            raise HTTPException(429, "Another import is running", headers={"Retry-After": "60"})
        try:
            recent = db.scalar(
                select(IngestionRun.id)
                .where(
                    IngestionRun.provider == provider,
                    IngestionRun.started_at > datetime.now(UTC) - timedelta(seconds=60),
                )
                .limit(1)
            )
            if recent:
                raise HTTPException(
                    429, "Import cooldown is 60 seconds", headers={"Retry-After": "60"}
                )
            yield
        finally:
            lock.execute(text("SELECT pg_advisory_unlock(824017)"))


@router.post("/artists", dependencies=[Depends(authorize)], status_code=201)
def import_artist(body: ImportRequest, db: Annotated[Session, Depends(get_db)]):
    settings = get_settings()
    if not settings.musicbrainz_user_agent:
        raise HTTPException(503, "An identifying MusicBrainz User-Agent must be configured")
    with import_slot(db, "musicbrainz"):
        provider = MusicBrainz(settings.musicbrainz_user_agent, settings.musicbrainz_max_releases)
        try:
            artist = ingest(db, lambda: provider.fetch_artist(body.artist_mbid))
        except (ProviderError, KeyError, ValueError):
            raise HTTPException(502, "MusicBrainz import failed; retry later") from None
        return {"id": str(artist.id), "name": artist.name, "provider": "musicbrainz"}


class SpotifyImportRequest(BaseModel):
    artist_id: str = Field(
        min_length=1,
        max_length=300,
        description="Spotify artist ID, spotify:artist: URI, or HTTPS artist share link",
    )

    @field_validator("artist_id")
    @classmethod
    def normalize_identifier(cls, value):
        return artist_identifier(value)


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


@router.post("/spotify/artists", dependencies=[Depends(authorize)], status_code=201)
def import_spotify_artist(body: SpotifyImportRequest, db: Annotated[Session, Depends(get_db)]):
    try:
        provider = get_spotify()
        with import_slot(db, "spotify"):
            artist = ingest(db, lambda: provider.fetch_artist(body.artist_id), "spotify")
        settings = get_settings()
        return {
            "id": str(artist.id),
            "name": artist.name,
            "provider": "spotify",
            "spotify_url": f"https://open.spotify.com/artist/{body.artist_id}",
            "import_scope": {
                "market": settings.spotify_market,
                "max_albums": settings.spotify_max_albums,
                "max_tracks_per_album": settings.spotify_max_tracks_per_album,
            },
        }
    except SpotifyError as exc:
        headers = {"Retry-After": str(exc.retry_after)} if exc.retry_after else None
        raise HTTPException(exc.status_code, str(exc), headers=headers) from None
    except (KeyError, ValueError, TypeError):
        raise HTTPException(
            502, "Spotify returned unusable metadata; no catalogue changes were saved"
        ) from None
