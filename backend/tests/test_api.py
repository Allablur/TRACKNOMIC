import uuid

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_db
from app.main import app
from app.services.ingestion import save_artist

pytestmark = pytest.mark.integration


@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def artist(db):
    item = save_artist(
        db,
        {
            "id": "api-test",
            "name": "API% Artist",
            "country": "ZA",
            "genres": ["test-api-genre"],
            "albums": [
                {
                    "id": "api-album",
                    "title": "API album",
                    "release_date": "2022",
                    "tracks": [{"id": "api-track", "title": "API track", "position": 1}],
                }
            ],
        },
        "test",
    )
    db.flush()
    return item


def test_search_detail_discography_and_unavailable_metrics(client, artist):
    result = client.get("/api/v1/artists/search", params={"q": "API%"}).json()
    assert result["total"] == 1
    assert result["items"][0]["followers"] is None
    assert result["items"][0]["sources"][0]["provider"] == "test"
    assert client.get(f"/api/v1/artists/{artist.id}").json()["album_count"] == 1
    assert client.get(f"/api/v1/artists/{artist.id}/albums").json()["items"][0]["track_count"] == 1


def test_analytics_filters_and_empty_catalogue(client, artist):
    params = {"q": "API%"}
    assert client.get("/api/v1/dashboard/overview", params=params).json()["tracks"] == 1
    assert client.get("/api/v1/analytics/genres", params=params).json()["items"] == [
        {"genre": "test-api-genre", "artists": 1}
    ]
    assert client.get("/api/v1/analytics/releases", params=params).json()["items"] == [
        {"year": 2022, "releases": 1}
    ]
    assert (
        client.get("/api/v1/dashboard/overview", params={"q": "missing-catalogue"}).json()[
            "artists"
        ]
        == 0
    )
    assert (
        client.get(
            "/api/v1/artists/search", params={"q": "API%", "provider": "musicbrainz"}
        ).json()["total"]
        == 0
    )


def test_compare_order_and_validation(client, artist, db):
    other = save_artist(db, {"id": "api-other", "name": "API Other"}, "test")
    response = client.get("/api/v1/artists/compare", params={"ids": f"{other.id},{artist.id}"})
    assert response.status_code == 200
    assert [a["name"] for a in response.json()["items"]] == ["API Other", "API% Artist"]
    for ids in [str(artist.id), f"{artist.id},{artist.id}", "bad,ids"]:
        assert client.get("/api/v1/artists/compare", params={"ids": ids}).status_code == 422
    assert client.get(f"/api/v1/artists/{uuid.uuid4()}").status_code == 404
    assert client.get("/api/v1/artists/search?limit=1000").status_code == 422


def test_ingestion_disabled_and_authorization(client, monkeypatch):
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "ingestion_enabled", False)
    body = {"artist_mbid": str(uuid.uuid4())}
    assert client.post("/api/v1/ingestion/artists", json=body).status_code == 503
    monkeypatch.setattr(settings, "ingestion_enabled", True)
    monkeypatch.setattr(settings, "ingestion_token", "unit-test-token-only")
    assert client.post("/api/v1/ingestion/artists", json=body).status_code == 401


def test_latest_metric_snapshot_preserves_real_zero(client, artist, db):
    from datetime import UTC, datetime

    from app.models import ArtistMetricSnapshot

    db.add_all(
        [
            ArtistMetricSnapshot(
                artist_id=artist.id,
                provider="test",
                captured_at=datetime(2020, 1, 1, tzinfo=UTC),
                followers=10,
                popularity=5,
            ),
            ArtistMetricSnapshot(
                artist_id=artist.id,
                provider="test",
                captured_at=datetime(2021, 1, 1, tzinfo=UTC),
                followers=0,
                popularity=None,
            ),
        ]
    )
    db.flush()
    data = client.get(f"/api/v1/artists/{artist.id}").json()
    assert data["followers"] == 0 and data["popularity"] is None
    assert data["metrics_provider"] == "test" and data["metrics_captured_at"].startswith("2021")
