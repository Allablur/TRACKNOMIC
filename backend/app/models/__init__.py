import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def now() -> datetime:
    return datetime.now(UTC)


artist_albums = Table(
    "artist_albums",
    Base.metadata,
    Column("artist_id", Uuid, ForeignKey("artists.id", ondelete="CASCADE"), primary_key=True),
    Column("album_id", Uuid, ForeignKey("albums.id", ondelete="CASCADE"), primary_key=True),
)
artist_genres = Table(
    "artist_genres",
    Base.metadata,
    Column("artist_id", Uuid, ForeignKey("artists.id", ondelete="CASCADE"), primary_key=True),
    Column("genre_id", Uuid, ForeignKey("genres.id", ondelete="CASCADE"), primary_key=True),
)


class Artist(Base):
    __tablename__ = "artists"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(300), index=True)
    country: Mapped[str | None] = mapped_column(String(3))
    type: Mapped[str | None] = mapped_column(String(80))
    disambiguation: Mapped[str | None] = mapped_column(Text)
    albums: Mapped[list["Album"]] = relationship(secondary=artist_albums, back_populates="artists")
    genres: Mapped[list["Genre"]] = relationship(secondary=artist_genres)


class Album(Base):
    __tablename__ = "albums"
    __table_args__ = (CheckConstraint("date_precision IN ('year','month','day','unknown')"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(500), index=True)
    # Keep partial source dates without fabricating month/day values.
    release_date: Mapped[str | None] = mapped_column(String(10), index=True)
    date_precision: Mapped[str] = mapped_column(String(10), default="unknown")
    release_type: Mapped[str | None] = mapped_column(String(80))
    artists: Mapped[list[Artist]] = relationship(secondary=artist_albums, back_populates="albums")
    tracks: Mapped[list["AlbumTrack"]] = relationship(cascade="all, delete-orphan")


class Track(Base):
    __tablename__ = "tracks"
    __table_args__ = (CheckConstraint("duration_ms IS NULL OR duration_ms >= 0"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(500))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    recording_identifier: Mapped[str | None] = mapped_column(String(100), unique=True)


class AlbumTrack(Base):
    __tablename__ = "album_tracks"
    __table_args__ = (CheckConstraint("disc_number > 0 AND position > 0"),)
    album_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("albums.id", ondelete="CASCADE"), primary_key=True
    )
    disc_number: Mapped[int] = mapped_column(primary_key=True)
    position: Mapped[int] = mapped_column(primary_key=True)
    track_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tracks.id", ondelete="CASCADE"), index=True
    )
    track: Mapped[Track] = relationship()


class Genre(Base):
    __tablename__ = "genres"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(150), unique=True)


class SourceMapping(Base):
    __tablename__ = "source_mappings"
    __table_args__ = (
        UniqueConstraint("entity_type", "provider", "external_id"),
        Index("ix_source_entity", "entity_type", "entity_id"),
        CheckConstraint("entity_type IN ('artist','album','track')"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    entity_type: Mapped[str] = mapped_column(String(20))
    entity_id: Mapped[uuid.UUID]
    provider: Mapped[str] = mapped_column(String(50))
    external_id: Mapped[str] = mapped_column(String(100))


class ArtistMetricSnapshot(Base):
    __tablename__ = "artist_metrics_snapshots"
    __table_args__ = (
        CheckConstraint("followers IS NULL OR followers >= 0"),
        CheckConstraint("popularity IS NULL OR (popularity >= 0 AND popularity <= 100)"),
        Index("ix_snapshot_artist_time", "artist_id", "captured_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    artist_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("artists.id", ondelete="CASCADE"))
    provider: Mapped[str] = mapped_column(String(50))
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    followers: Mapped[int | None]
    popularity: Mapped[int | None]


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"
    __table_args__ = (
        CheckConstraint("status IN ('running','succeeded','failed')"),
        Index("ix_ingestion_provider_started", "provider", "started_at"),
        Index("ix_ingestion_provider_retry", "provider", "retry_after_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    provider: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(20), default="running")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
    retry_after_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SpotifyImportBatch(Base):
    __tablename__ = "spotify_import_batches"
    __table_args__ = (CheckConstraint("status IN ('active','paused','cancelled','completed')"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    request_id: Mapped[uuid.UUID] = mapped_column(Uuid, unique=True)
    name: Mapped[str] = mapped_column(String(80), default="Spotify bulk import")
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    items: Mapped[list["SpotifyImportItem"]] = relationship(
        cascade="all, delete-orphan", order_by="SpotifyImportItem.position"
    )


class SpotifyImportItem(Base):
    __tablename__ = "spotify_import_items"
    __table_args__ = (
        UniqueConstraint("batch_id", "spotify_id"),
        CheckConstraint("status IN ('pending','running','succeeded','failed','cancelled')"),
        CheckConstraint("position > 0 AND attempts >= 0"),
        Index("ix_spotify_import_ready", "status", "available_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    batch_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("spotify_import_batches.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int]
    spotify_id: Mapped[str] = mapped_column(String(22))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    attempts: Mapped[int] = mapped_column(default=0)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    artist_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("artists.id", ondelete="SET NULL")
    )
    artist_name: Mapped[str | None] = mapped_column(String(300))
    error: Mapped[str | None] = mapped_column(Text)
    last_http_status: Mapped[int | None]
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
