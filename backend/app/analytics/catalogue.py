from typing import Literal

import numpy as np
import pandas as pd
from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    Album,
    AlbumTrack,
    Artist,
    ArtistMetricSnapshot,
    Genre,
    SourceMapping,
    artist_albums,
    artist_genres,
)

Provider = Literal["all", "demo", "musicbrainz"]


def artist_scope(provider: str = "all", q: str = "", country: str = ""):
    statement = select(Artist)
    if provider != "all":
        statement = statement.where(
            Artist.id.in_(
                select(SourceMapping.entity_id).where(
                    SourceMapping.entity_type == "artist", SourceMapping.provider == provider
                )
            )
        )
    if q:
        # Escape LIKE metacharacters: search is literal text, not a user SQL pattern.
        escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        statement = statement.where(Artist.name.ilike(f"%{escaped}%", escape="\\"))
    if country:
        statement = statement.where(Artist.country == country.upper())
    return statement


def scoped_albums(provider="all", q="", country=""):
    artists = artist_scope(provider, q, country).with_only_columns(Artist.id)
    return select(Album).where(
        Album.id.in_(select(artist_albums.c.album_id).where(artist_albums.c.artist_id.in_(artists)))
    )


def artist_options():
    return [selectinload(Artist.genres), selectinload(Artist.albums)]


def artists_json(db: Session, artists: list[Artist]) -> list[dict]:
    ids = [a.id for a in artists]
    if not ids:
        return []
    sources = {}
    for mapping in db.scalars(
        select(SourceMapping).where(
            SourceMapping.entity_type == "artist", SourceMapping.entity_id.in_(ids)
        )
    ):
        sources.setdefault(mapping.entity_id, []).append(
            {"provider": mapping.provider, "external_id": mapping.external_id}
        )
    ranked = (
        select(
            ArtistMetricSnapshot.id,
            func.row_number()
            .over(
                partition_by=ArtistMetricSnapshot.artist_id,
                order_by=(ArtistMetricSnapshot.captured_at.desc(), ArtistMetricSnapshot.id.desc()),
            )
            .label("rank"),
        )
        .where(ArtistMetricSnapshot.artist_id.in_(ids))
        .subquery()
    )
    snapshots = {
        snapshot.artist_id: snapshot
        for snapshot in db.scalars(
            select(ArtistMetricSnapshot)
            .join(ranked, ranked.c.id == ArtistMetricSnapshot.id)
            .where(ranked.c.rank == 1)
        )
    }
    album_ids = {album.id for artist in artists for album in artist.albums}
    track_counts = (
        dict(
            db.execute(
                select(AlbumTrack.album_id, func.count())
                .where(AlbumTrack.album_id.in_(album_ids))
                .group_by(AlbumTrack.album_id)
            ).all()
        )
        if album_ids
        else {}
    )
    result = []
    for artist in artists:
        snapshot = snapshots.get(artist.id)
        result.append(
            {
                "id": str(artist.id),
                "name": artist.name,
                "country": artist.country,
                "type": artist.type,
                "disambiguation": artist.disambiguation,
                "genres": sorted(g.name for g in artist.genres),
                "album_count": len(artist.albums),
                "track_count": sum(track_counts.get(a.id, 0) for a in artist.albums),
                "followers": snapshot.followers if snapshot else None,
                "popularity": snapshot.popularity if snapshot else None,
                "metrics_provider": snapshot.provider if snapshot else None,
                "metrics_captured_at": snapshot.captured_at.isoformat() if snapshot else None,
                "sources": sources.get(artist.id, []),
            }
        )
    return result


def albums_json(db: Session, albums: list[Album]) -> list[dict]:
    ids = [a.id for a in albums]
    counts = (
        dict(
            db.execute(
                select(AlbumTrack.album_id, func.count())
                .where(AlbumTrack.album_id.in_(ids))
                .group_by(AlbumTrack.album_id)
            ).all()
        )
        if ids
        else {}
    )
    sources = {}
    for mapping in db.scalars(
        select(SourceMapping).where(
            SourceMapping.entity_type == "album", SourceMapping.entity_id.in_(ids)
        )
    ):
        sources.setdefault(mapping.entity_id, []).append(
            {"provider": mapping.provider, "external_id": mapping.external_id}
        )
    return [
        {
            "id": str(a.id),
            "title": a.title,
            "release_date": a.release_date,
            "date_precision": a.date_precision,
            "release_type": a.release_type,
            "track_count": counts.get(a.id, 0),
            "artists": [{"id": str(artist.id), "name": artist.name} for artist in a.artists],
            "sources": sources.get(a.id, []),
        }
        for a in albums
    ]


def overview(db: Session, provider="all", q="", country="") -> dict:
    artists = artist_scope(provider, q, country).with_only_columns(Artist.id)
    albums = scoped_albums(provider, q, country).with_only_columns(Album.id)
    artist_count = db.scalar(select(func.count()).select_from(artists.subquery()))
    album_count = db.scalar(select(func.count()).select_from(albums.subquery()))
    tracks = db.scalar(
        select(func.count(distinct(AlbumTrack.track_id))).where(AlbumTrack.album_id.in_(albums))
    )
    return {
        "artists": artist_count,
        "albums": album_count,
        "tracks": tracks,
        "provider": provider,
        "scope": "Tracked catalogue, not global popularity",
        "demo_included": provider != "musicbrainz"
        and bool(
            db.scalar(
                select(func.count())
                .select_from(SourceMapping)
                .where(
                    SourceMapping.provider == "demo",
                    SourceMapping.entity_type == "artist",
                    SourceMapping.entity_id.in_(artists),
                )
            )
        ),
        "followers": None,
        "popularity": None,
    }


def genres(db: Session, provider="all", q="", country="") -> list[dict]:
    artists = artist_scope(provider, q, country).with_only_columns(Artist.id)
    rows = db.execute(
        select(Genre.name, func.count(distinct(artist_genres.c.artist_id)))
        .join(artist_genres, Genre.id == artist_genres.c.genre_id)
        .where(artist_genres.c.artist_id.in_(artists))
        .group_by(Genre.name)
        .order_by(Genre.name)
    ).all()
    return [{"genre": name, "artists": count} for name, count in rows]


def releases(db: Session, provider="all", q="", country="") -> list[dict]:
    albums = scoped_albums(provider, q, country).with_only_columns(Album.id)
    year_bucket = func.substr(Album.release_date, 1, 4)
    rows = db.execute(
        select(year_bucket, func.count())
        .where(Album.id.in_(albums), Album.release_date.is_not(None))
        .group_by(year_bucket)
    ).all()
    frame = pd.DataFrame(rows, columns=["year", "releases"])
    if frame.empty:
        return []
    frame = frame[frame["year"].str.fullmatch(r"\d{4}")]
    if frame.empty:
        return []
    frame["year"] = frame["year"].astype(int)
    frame = frame.sort_values("year")
    # Explicit gaps distinguish zero releases from an absent chart bucket.
    full_years = np.arange(int(frame.year.min()), int(frame.year.max()) + 1)
    frame = (
        frame.set_index("year").reindex(full_years, fill_value=0).rename_axis("year").reset_index()
    )
    return frame.to_dict(orient="records")
