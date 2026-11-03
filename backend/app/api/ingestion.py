import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.core.config import get_settings
from app.core.database import engine
from app.models import IngestionRun
from app.providers.musicbrainz import MusicBrainz, ProviderError
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
    if not settings.musicbrainz_user_agent:
        raise HTTPException(503, "An identifying MusicBrainz User-Agent must be configured")


class ImportRequest(BaseModel):
    artist_mbid: UUID


@router.post("/artists", dependencies=[Depends(authorize)], status_code=201)
def import_artist(body: ImportRequest, db: Annotated[Session, Depends(get_db)]):
    # A separate connection holds the session advisory lock across import commits.
    # This serializes provider access across API workers, including the cooldown check.
    with engine.connect() as lock:
        acquired = lock.scalar(text("SELECT pg_try_advisory_lock(824017)"))
        if not acquired:
            raise HTTPException(429, "Another import is running", headers={"Retry-After": "60"})
        try:
            recent = db.scalar(
                select(IngestionRun.id)
                .where(
                    IngestionRun.provider == "musicbrainz",
                    IngestionRun.started_at > datetime.now(UTC) - timedelta(seconds=60),
                )
                .limit(1)
            )
            if recent:
                raise HTTPException(
                    429, "Import cooldown is 60 seconds", headers={"Retry-After": "60"}
                )
            settings = get_settings()
            provider = MusicBrainz(
                settings.musicbrainz_user_agent, settings.musicbrainz_max_releases
            )
            try:
                artist = ingest(db, lambda: provider.fetch_artist(body.artist_mbid))
            except (ProviderError, KeyError, ValueError):
                raise HTTPException(502, "MusicBrainz import failed; retry later") from None
            return {"id": str(artist.id), "name": artist.name, "provider": "musicbrainz"}
        finally:
            lock.execute(text("SELECT pg_advisory_unlock(824017)"))
