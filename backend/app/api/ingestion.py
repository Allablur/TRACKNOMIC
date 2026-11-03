import secrets
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.core.config import get_settings
from app.providers.musicbrainz import MusicBrainz, ProviderError
from app.providers.spotify import SpotifyError, artist_identifier
from app.services.import_control import import_slot
from app.services.ingestion import ingest
from app.services.spotify_import import get_spotify, perform_spotify_import

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


@router.post("/spotify/artists", dependencies=[Depends(authorize)], status_code=201)
def import_spotify_artist(body: SpotifyImportRequest, db: Annotated[Session, Depends(get_db)]):
    try:
        return perform_spotify_import(db, body.artist_id, get_spotify())
    except SpotifyError as exc:
        headers = {"Retry-After": str(exc.retry_after)} if exc.retry_after else None
        raise HTTPException(exc.status_code, str(exc), headers=headers) from None
    except (KeyError, ValueError, TypeError):
        raise HTTPException(
            502, "Spotify returned unusable metadata; no catalogue changes were saved"
        ) from None
