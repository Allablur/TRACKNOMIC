"""Statistics from saved catalogue rows; never estimates of audience or streams."""

import re
from collections import Counter
from datetime import UTC, date, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Album, AlbumTrack, Track, artist_albums


def catalogue_stats(db: Session, artist_id) -> dict:
    album_ids = select(artist_albums.c.album_id).where(artist_albums.c.artist_id == artist_id)
    releases = db.execute(
        select(Album.id, Album.title, Album.release_type, Album.release_date, Album.date_precision)
        .where(Album.id.in_(album_ids))
        .order_by(Album.id)
    ).all()
    kinds = Counter((row.release_type or "").lower() for row in releases)
    positions = db.scalar(
        select(func.count()).select_from(AlbumTrack).where(AlbumTrack.album_id.in_(album_ids))
    )
    # A recording reused on several editions contributes once, even when durations match.
    track_ids = select(AlbumTrack.track_id).where(AlbumTrack.album_id.in_(album_ids))
    tracks, known, duration, average = db.execute(
        select(
            func.count(Track.id),
            func.count(Track.duration_ms),
            func.sum(Track.duration_ms),
            func.avg(Track.duration_ms),
        ).where(Track.id.in_(track_ids))
    ).one()
    dated = []
    for row in releases:
        value = row.release_date or ""
        if not re.fullmatch(r"\d{4}(?:-\d{2}){0,2}", value):
            continue
        try:
            # Only an internal sorting key; the API preserves the source's partial date.
            key = date.fromisoformat(value + {4: "-01-01", 7: "-01", 10: ""}[len(value)])
        except ValueError:
            continue
        dated.append((key, row))
    years = Counter(key.year for key, _ in dated)
    latest = (
        max(dated, key=lambda item: (item[0], item[1].release_date, str(item[1].id)))[1]
        if dated
        else None
    )
    return {
        "artist_id": str(artist_id),
        "calculated_at": datetime.now(UTC).isoformat(),
        "scope": "Saved release editions and distinct track IDs; partial imports may be incomplete",
        "release_count": len(releases),
        "album_count": kinds["album"],
        "single_ep_count": kinds["single"] + kinds["ep"],
        "compilation_count": kinds["compilation"],
        "other_release_count": sum(
            count
            for kind, count in kinds.items()
            if kind not in {"album", "single", "ep", "compilation"}
        ),
        "distinct_track_count": tracks,
        "track_position_count": positions,
        "known_duration_track_count": known,
        "known_duration_ms": duration,
        "average_known_duration_ms": round(average) if average is not None else None,
        "undated_release_count": len(releases) - len(dated),
        "latest_release": {
            "id": str(latest.id),
            "title": latest.title,
            "release_date": latest.release_date,
            "date_precision": latest.date_precision,
        }
        if latest
        else None,
        "releases_by_year": [
            {"year": year, "releases": years[year]} for year in range(min(years), max(years) + 1)
        ]
        if years
        else [],
    }
