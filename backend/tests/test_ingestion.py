import uuid
from unittest.mock import patch

import httpx
import pytest
from sqlalchemy import func, select

from app.models import Artist, IngestionRun, SourceMapping
from app.providers.musicbrainz import MusicBrainz, ProviderError
from app.services.ingestion import ingest


@pytest.mark.integration
def test_import_is_idempotent_and_attributed(db):
    payload = {
        "id": "test-import",
        "name": "Import test",
        "genres": ["Jazz"],
        "albums": [
            {
                "id": "test-release",
                "title": "Test",
                "release_date": "2024-06",
                "tracks": [{"id": "recording-1", "title": "Test track", "position": 1}],
            }
        ],
    }
    first = ingest(db, lambda: payload, "test")
    second = ingest(db, lambda: payload, "test")
    assert first.id == second.id
    assert len(second.albums[0].tracks) == 1
    assert second.albums[0].date_precision == "month"
    assert (
        db.scalar(
            select(func.count()).select_from(SourceMapping).where(SourceMapping.provider == "test")
        )
        == 3
    )


@pytest.mark.integration
def test_failed_import_records_failure_and_rolls_back(db):
    def broken():
        db.add(Artist(name="Should roll back"))
        db.flush()
        raise ProviderError("failure")

    with pytest.raises(ProviderError):
        ingest(db, broken, "test")
    assert db.scalar(select(Artist).where(Artist.name == "Should roll back")) is None
    assert db.scalar(select(IngestionRun).where(IngestionRun.provider == "test")).status == "failed"


def test_provider_identification_retry_and_null_metrics():
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(503)
        if "/artist/" in str(request.url):
            return httpx.Response(200, json={"id": str(uuid.uuid4()), "name": "Test", "tags": []})
        return httpx.Response(200, json={"releases": []})

    provider = MusicBrainz(
        "Trackonomics/0.1 (https://github.com/Allablur/TRACKNOMIC)",
        transport=httpx.MockTransport(handler),
    )
    with patch("app.providers.musicbrainz.time.sleep") as sleep:
        result = provider.fetch_artist(uuid.uuid4())
    assert "followers" not in result
    assert len(calls) == 3 and sleep.call_count >= 3
    assert all(r.headers["User-Agent"].startswith("Trackonomics/") for r in calls)


def test_missing_identification_and_upstream_failure():
    with pytest.raises(ValueError):
        MusicBrainz("")
    provider = MusicBrainz(
        "Test/1 (test)", transport=httpx.MockTransport(lambda _: httpx.Response(404))
    )
    with patch("app.providers.musicbrainz.time.sleep"), pytest.raises(ProviderError):
        provider.fetch_artist(uuid.uuid4())


def test_provider_normalizes_release_media_and_preserves_missing_duration():
    artist_id, release_id, recording_id = [str(uuid.uuid4()) for _ in range(3)]

    def handler(request):
        if "/artist/" in request.url.path:
            return httpx.Response(
                200, json={"id": artist_id, "name": "Provider fixture", "tags": [{"name": "jazz"}]}
            )
        if request.url.path.endswith("/release"):
            return httpx.Response(200, json={"releases": [{"id": release_id}]})
        return httpx.Response(
            200,
            json={
                "id": release_id,
                "title": "Release fixture",
                "date": "2024-06",
                "release-group": {"primary-type": "Album"},
                "media": [
                    {
                        "position": 2,
                        "tracks": [
                            {
                                "id": str(uuid.uuid4()),
                                "position": 1,
                                "recording": {"id": recording_id, "title": "Recording fixture"},
                            }
                        ],
                    }
                ],
            },
        )

    provider = MusicBrainz("Test/1 (offline)", transport=httpx.MockTransport(handler))
    with patch("app.providers.musicbrainz.time.sleep"):
        data = provider.fetch_artist(uuid.UUID(artist_id))
    assert data["genres"] == ["jazz"]
    album = data["albums"][0]
    assert album["release_date"] == "2024-06" and album["release_type"] == "Album"
    assert album["tracks"][0] == {
        "id": recording_id,
        "title": "Recording fixture",
        "duration_ms": None,
        "disc_number": 2,
        "position": 1,
    }


def test_provider_stops_after_bounded_retries():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(503)

    provider = MusicBrainz("Test/1 (offline)", transport=httpx.MockTransport(handler))
    with patch("app.providers.musicbrainz.time.sleep"), pytest.raises(ProviderError):
        provider.fetch_artist(uuid.uuid4())
    assert len(calls) == 3


@pytest.mark.integration
def test_mid_import_constraint_failure_preserves_previous_catalogue(db):
    import copy

    from sqlalchemy.exc import IntegrityError

    payload = {
        "id": "rollback-test",
        "name": "Before",
        "albums": [
            {
                "id": "rollback-release",
                "title": "Before release",
                "tracks": [{"id": "rollback-track", "title": "Before track", "position": 1}],
            }
        ],
    }
    artist = ingest(db, lambda: payload, "test")
    artist_id = artist.id
    bad = copy.deepcopy(payload)
    bad["name"] = "After"
    bad["albums"][0]["tracks"][0]["position"] = 0
    with pytest.raises(IntegrityError):
        ingest(db, lambda: bad, "test")
    restored = db.get(Artist, artist_id)
    assert restored.name == "Before"
    assert len(restored.albums[0].tracks) == 1
    assert restored.albums[0].tracks[0].position == 1
