from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Album, AlbumTrack, Artist, Genre, IngestionRun, SourceMapping, Track


def mapped_entity(db: Session, kind: str, provider: str, external_id: str, model, **fields):
    mapping = db.scalar(
        select(SourceMapping).where(
            SourceMapping.entity_type == kind,
            SourceMapping.provider == provider,
            SourceMapping.external_id == external_id,
        )
    )
    entity = db.get(model, mapping.entity_id) if mapping else None
    if entity is None:
        entity = model(**fields)
        db.add(entity)
        db.flush()
        db.add(
            SourceMapping(
                entity_type=kind, entity_id=entity.id, provider=provider, external_id=external_id
            )
        )
    else:
        for key, value in fields.items():
            setattr(entity, key, value)
    db.flush()
    return entity


def save_artist(db: Session, payload: dict, provider: str) -> Artist:
    artist = mapped_entity(
        db,
        "artist",
        provider,
        payload["id"],
        Artist,
        **{key: payload.get(key) for key in ("name", "country", "type", "disambiguation")},
    )
    genres = []
    for name in sorted(set(g.strip().lower() for g in payload.get("genres", []) if g.strip())):
        genre = db.scalar(select(Genre).where(Genre.name == name))
        if genre is None:
            genre = Genre(name=name)
            db.add(genre)
            db.flush()
        genres.append(genre)
    artist.genres = genres
    for item in payload.get("albums", []):
        date = item.get("release_date") or None
        precision = {4: "year", 7: "month", 10: "day"}.get(len(date or ""), "unknown")
        album = mapped_entity(
            db,
            "album",
            provider,
            item["id"],
            Album,
            title=item["title"],
            release_date=date,
            date_precision=precision,
            release_type=item.get("release_type"),
        )
        if artist not in album.artists:
            album.artists.append(artist)
        # Replace this release's positions transactionally; re-import is idempotent.
        album.tracks.clear()
        db.flush()
        for track in item.get("tracks", []):
            recording = mapped_entity(
                db,
                "track",
                provider,
                track["id"],
                Track,
                title=track["title"],
                duration_ms=track.get("duration_ms"),
                recording_identifier=f"{provider}:{track['id']}",
            )
            album.tracks.append(
                AlbumTrack(
                    track=recording,
                    disc_number=track.get("disc_number", 1),
                    position=track["position"],
                )
            )
    db.flush()
    return artist


def ingest(db: Session, fetch, provider: str = "musicbrainz") -> Artist:
    run = IngestionRun(provider=provider)
    db.add(run)
    db.commit()
    run_id = run.id
    try:
        artist = save_artist(db, fetch(), provider)
        run.status = "succeeded"
        run.finished_at = datetime.now(UTC)
        db.commit()
        return artist
    except Exception:
        db.rollback()
        failed = db.get(IngestionRun, run_id)
        failed.status = "failed"
        failed.finished_at = datetime.now(UTC)
        failed.error = "Import failed; no catalogue changes were committed."
        db.commit()
        raise
