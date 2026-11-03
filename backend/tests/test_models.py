import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from app.models import Album, AlbumTrack, Artist, ArtistMetricSnapshot, Genre, SourceMapping, Track

pytestmark = pytest.mark.integration


def test_schema_contains_all_domain_tables(db):
    assert {
        "artists",
        "albums",
        "tracks",
        "artist_albums",
        "album_tracks",
        "genres",
        "artist_genres",
        "source_mappings",
        "artist_metrics_snapshots",
        "ingestion_runs",
    } <= set(inspect(db.bind).get_table_names())


def test_relationships_partial_dates_and_nullable_metrics(db):
    artist = Artist(name="Model test", genres=[Genre(name="test-genre")])
    album = Album(
        title="Partial date", release_date="2024", date_precision="year", artists=[artist]
    )
    track = Track(title="Recording", duration_ms=1000)
    album.tracks.append(AlbumTrack(track=track, disc_number=1, position=1))
    db.add(album)
    db.flush()
    snapshot = ArtistMetricSnapshot(artist_id=artist.id, provider="musicbrainz")
    db.add(snapshot)
    db.flush()
    assert snapshot.followers is None and snapshot.popularity is None
    assert artist.albums[0].release_date == "2024"
    assert album.tracks[0].track.title == "Recording"


def test_source_identifiers_are_unique(db):
    import uuid

    for _ in range(2):
        db.add(
            SourceMapping(
                entity_type="artist",
                entity_id=uuid.uuid4(),
                provider="test",
                external_id="duplicate",
            )
        )
    with pytest.raises(IntegrityError):
        db.flush()
