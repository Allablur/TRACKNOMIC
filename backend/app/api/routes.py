from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.analytics.artist_stats import catalogue_stats
from app.analytics.catalogue import (
    Provider,
    albums_json,
    artist_options,
    artist_scope,
    artists_json,
    genres,
    overview,
    releases,
    scoped_albums,
)
from app.api.dependencies import get_db
from app.models import Album, Artist

router = APIRouter(prefix="/api/v1")
DB = Annotated[Session, Depends(get_db)]


@router.get("/dashboard/overview", tags=["analytics"])
def dashboard(
    db: DB,
    provider: Provider = "spotify",
    q: str = Query("", max_length=150),
    country: str = Query("", max_length=3),
):
    return overview(db, provider, q, country)


@router.get("/artists/search", tags=["artists"])
def search_artists(
    db: DB,
    q: str = Query("", max_length=150),
    provider: Provider = "spotify",
    country: str = Query("", max_length=3),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    statement = artist_scope(provider, q, country)
    total = db.scalar(select(func.count()).select_from(statement.subquery()))
    items = db.scalars(
        statement.options(*artist_options())
        .order_by(Artist.name, Artist.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return {
        "items": artists_json(db, list(items)),
        "total": total,
        "limit": limit,
        "offset": offset,
    }


# Static compare route must precede the UUID route.
@router.get("/artists/compare", tags=["artists"])
def compare_artists(db: DB, ids: str = Query(max_length=200)):
    try:
        parsed = [UUID(value.strip()) for value in ids.split(",")]
    except ValueError:
        raise HTTPException(422, "Provide comma-separated artist UUIDs") from None
    if not 2 <= len(parsed) <= 5 or len(set(parsed)) != len(parsed):
        raise HTTPException(422, "Compare two to five distinct artists")
    artists = db.scalars(
        select(Artist).where(Artist.id.in_(parsed)).options(*artist_options())
    ).all()
    if len(artists) != len(parsed):
        raise HTTPException(404, "One or more artists were not found")
    indexed = {item["id"]: item for item in artists_json(db, list(artists))}
    return {
        "items": [indexed[str(id)] for id in parsed],
        "scope": "Tracked catalogue; unavailable metrics are null",
    }


@router.get("/artists/{artist_id}", tags=["artists"])
def artist_detail(artist_id: UUID, db: DB):
    artist = db.scalar(select(Artist).where(Artist.id == artist_id).options(*artist_options()))
    if artist is None:
        raise HTTPException(404, "Artist not found")
    return artists_json(db, [artist])[0]


@router.get("/artists/{artist_id}/albums", tags=["artists"])
def artist_albums(artist_id: UUID, db: DB):
    artist = db.get(Artist, artist_id)
    if artist is None:
        raise HTTPException(404, "Artist not found")
    items = db.scalars(
        select(Album)
        .where(Album.artists.any(id=artist_id))
        .options(selectinload(Album.artists))
        .order_by(Album.release_date.desc().nulls_last(), Album.id)
    ).all()
    return {"items": albums_json(db, list(items))}


@router.get("/artists/{artist_id}/catalogue-stats", tags=["analytics"])
def artist_catalogue_stats(artist_id: UUID, db: DB):
    if db.get(Artist, artist_id) is None:
        raise HTTPException(404, "Artist not found")
    return catalogue_stats(db, artist_id)


@router.get("/albums", tags=["albums"])
def album_list(
    db: DB,
    provider: Provider = "spotify",
    q: str = Query("", max_length=150),
    country: str = Query("", max_length=3),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    statement = scoped_albums(provider, q, country)
    total = db.scalar(select(func.count()).select_from(statement.subquery()))
    items = db.scalars(
        statement.options(selectinload(Album.artists))
        .order_by(Album.release_date.desc().nulls_last(), Album.id)
        .offset(offset)
        .limit(limit)
    ).all()
    return {"items": albums_json(db, list(items)), "total": total, "limit": limit, "offset": offset}


@router.get("/analytics/genres", tags=["analytics"])
def genre_distribution(
    db: DB,
    provider: Provider = "spotify",
    q: str = Query("", max_length=150),
    country: str = Query("", max_length=3),
):
    return {
        "items": genres(db, provider, q, country),
        "scope": "An artist may have multiple genres",
    }


@router.get("/analytics/releases", tags=["analytics"])
def release_trends(
    db: DB,
    provider: Provider = "spotify",
    q: str = Query("", max_length=150),
    country: str = Query("", max_length=3),
):
    return {
        "items": releases(db, provider, q, country),
        "scope": "Release editions with known dates only",
    }
