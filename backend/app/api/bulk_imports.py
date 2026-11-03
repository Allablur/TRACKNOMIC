from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import AfterValidator, BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.api.ingestion import authorize
from app.core.config import get_settings
from app.providers.spotify import SpotifyError, artist_identifier
from app.services.bulk_imports import batch_json, change_batch, create_batch, load_batch
from app.services.spotify_import import get_spotify

router = APIRouter(
    prefix="/api/v1/ingestion/spotify/batches",
    tags=["bulk imports"],
    dependencies=[Depends(authorize)],
)
DB = Annotated[Session, Depends(get_db)]
ArtistInput = Annotated[str, Field(min_length=1, max_length=300), AfterValidator(artist_identifier)]


class BatchRequest(BaseModel):
    request_id: UUID
    artist_ids: list[ArtistInput] = Field(min_length=1, max_length=100)
    import_mode: Literal["full"] = "full"
    release_types: list[Literal["album", "single", "compilation", "appears_on"]] = Field(
        default_factory=lambda: ["album", "single", "compilation"], min_length=1, max_length=4
    )
    name: str = Field(default="Spotify bulk import", min_length=1, max_length=80)

    @field_validator("release_types")
    @classmethod
    def normalize_groups(cls, values):
        return [
            group for group in ["album", "single", "compilation", "appears_on"] if group in values
        ]

    @field_validator("artist_ids")
    @classmethod
    def remove_duplicates(cls, values):
        return list(dict.fromkeys(values))


def require_worker():
    if not get_settings().bulk_worker_enabled:
        raise HTTPException(503, "Background imports are disabled on the API server")
    try:
        get_spotify()  # Validate presence, not live Spotify authorization.
    except SpotifyError as exc:
        raise HTTPException(exc.status_code, str(exc)) from None


@router.get("/access")
def access(response: Response):
    require_worker()
    response.headers["Cache-Control"] = "no-store"
    return {"configured": True, "max_artists": 100, "full_discography": True}


@router.post("", status_code=202)
def queue(body: BatchRequest, db: DB, response: Response):
    require_worker()
    response.headers["Cache-Control"] = "no-store"
    return batch_json(
        db,
        create_batch(
            db,
            body.artist_ids,
            body.name,
            body.request_id,
            import_mode="full",
            release_types=body.release_types,
        ),
    )


@router.get("/{batch_id}")
def progress(batch_id: UUID, db: DB, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return batch_json(db, load_batch(db, batch_id))


@router.post("/{batch_id}/{action}")
def control(
    batch_id: UUID,
    action: Literal["pause", "resume", "cancel", "retry"],
    db: DB,
    response: Response,
):
    response.headers["Cache-Control"] = "no-store"
    return batch_json(db, change_batch(db, batch_id, action))
