from unittest.mock import patch

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import func, select

from app.core.config import Settings, get_settings
from app.models import ArtistMetricSnapshot, IngestionRun, SourceMapping
from app.providers.spotify import Spotify, SpotifyError, artist_identifier
from app.services.ingestion import ingest, save_artist

ARTIST_ID, ALBUM_ID, TRACK_ID = "A" * 22, "B" * 22, "C" * 22
# All responses below are synthetic test fixtures, never runtime fallback data.


def spotify_client(handler, **kwargs):
    return Spotify(
        "offline-test-client",
        "offline-test-secret",
        transport=httpx.MockTransport(handler),
        **kwargs,
    )


def authorize(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "ingestion_enabled", True)
    monkeypatch.setattr(settings, "ingestion_token", "test-" + "x" * 32)
    return {"Authorization": "Bearer " + settings.ingestion_token}


@pytest.mark.parametrize(
    "value",
    [
        ARTIST_ID,
        "spotify:artist:" + ARTIST_ID,
        "https://open.spotify.com/artist/" + ARTIST_ID + "?si=share",
        "https://open.spotify.com/intl-en/artist/" + ARTIST_ID,
    ],
)
def test_artist_identifiers(value):
    assert artist_identifier(value) == ARTIST_ID


@pytest.mark.parametrize(
    "value",
    [
        "not-an-id",
        "https://evil.example/artist/" + ARTIST_ID,
        "https://open.spotify.com/album/" + ARTIST_ID,
        "https://open.spotify.com@evil.example/artist/" + ARTIST_ID,
    ],
)
def test_arbitrary_urls_and_wrong_entities_rejected(value):
    with pytest.raises(ValueError):
        artist_identifier(value)


def test_oauth_pagination_cache_attribution_and_missing_fields():
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.host == "accounts.spotify.com":
            assert request.method == "POST" and request.headers["Authorization"].startswith(
                "Basic "
            )
            assert request.content == b"grant_type=client_credentials"
            return httpx.Response(200, json={"access_token": "offline-token", "expires_in": 3600})
        assert request.headers["Authorization"] == "Bearer offline-token"
        assert request.url.host == "api.spotify.com"
        if request.url.path.endswith("/artists/" + ARTIST_ID):
            return httpx.Response(200, json={"id": ARTIST_ID, "name": "Spotify provider test"})
        assert request.url.params["market"] == "ZA"
        if request.url.path.endswith("/albums"):
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": ALBUM_ID,
                            "name": "Test release",
                            "release_date": "2024-06",
                            "album_type": "album",
                        }
                    ],
                    "next": None,
                },
            )
        offset = int(request.url.params["offset"])
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": TRACK_ID if offset == 0 else "D" * 22,
                        "name": "Test recording",
                        "track_number": offset + 1,
                        "disc_number": 1,
                    }
                ],
                "next": "https://evil.example/steal" if offset == 0 else None,
            },
        )

    provider = spotify_client(handler)
    payload = provider.fetch_artist(ARTIST_ID)
    assert payload["country"] is None and payload["genres"] == []
    assert payload["metrics"] == {"followers": None, "popularity": None}
    assert payload["albums"][0]["release_date"] == "2024-06"
    tracks = payload["albums"][0]["tracks"]
    assert len(tracks) == 2 and tracks[0]["duration_ms"] is None
    provider.fetch_artist(ARTIST_ID)
    assert sum(r.url.host == "accounts.spotify.com" for r in requests) == 1
    assert all(r.url.host in {"accounts.spotify.com", "api.spotify.com"} for r in requests)


def test_expired_bearer_is_refreshed_once_and_real_zero_is_preserved():
    tokens = []

    def handler(request):
        if request.url.host == "accounts.spotify.com":
            tokens.append(1)
            return httpx.Response(
                200, json={"access_token": f"token-{len(tokens)}", "expires_in": 3600}
            )
        if request.headers["Authorization"] == "Bearer token-1":
            return httpx.Response(401)
        if request.url.path.endswith("/artists/" + ARTIST_ID):
            return httpx.Response(
                200,
                json={
                    "id": ARTIST_ID,
                    "name": "Token test",
                    "followers": {"total": 0},
                    "popularity": 0,
                },
            )
        return httpx.Response(200, json={"items": [], "next": None})

    data = spotify_client(handler).fetch_artist(ARTIST_ID)
    assert len(tokens) == 2 and data["metrics"] == {"followers": 0, "popularity": 0}


@pytest.mark.parametrize("status,expected", [(403, 403), (404, 404), (503, 502)])
def test_access_errors_are_bounded_and_do_not_expose_upstream_bodies(status, expected):
    calls = []

    def handler(request):
        if request.url.host == "accounts.spotify.com":
            return httpx.Response(200, json={"access_token": "private-token", "expires_in": 3600})
        calls.append(1)
        return httpx.Response(status, text="upstream private credential details")

    with patch("app.providers.spotify.time.sleep"), pytest.raises(SpotifyError) as error:
        spotify_client(handler).fetch_artist(ARTIST_ID)
    assert error.value.status_code == expected
    assert "private" not in str(error.value)
    assert len(calls) == (3 if status == 503 else 1)


def test_rate_limit_is_propagated_without_sleep_or_automatic_retry():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(429, headers={"Retry-After": "120"}, text="private body")

    provider = spotify_client(handler)
    for _ in range(2):
        with pytest.raises(SpotifyError) as error:
            provider.fetch_artist(ARTIST_ID)
        assert error.value.status_code == 429 and 119 <= error.value.retry_after <= 120
        assert "private" not in str(error.value)
    assert len(calls) == 1


def test_missing_credentials_and_secret_redaction():
    with pytest.raises(SpotifyError) as error:
        Spotify("", "")
    assert error.value.status_code == 503
    settings = Settings(_env_file=None, spotify_client_secret="offline-hidden-secret")
    assert "offline-hidden-secret" not in repr(settings)
    assert isinstance(settings.spotify_client_secret, SecretStr)


def test_invalid_token_response_never_yields_a_request_with_empty_bearer():
    provider = spotify_client(lambda _: httpx.Response(200, json={"expires_in": 3600}))
    with pytest.raises(SpotifyError, match="invalid authorization"):
        provider.fetch_artist(ARTIST_ID)


@pytest.mark.integration
def test_spotify_api_import_defaults_snapshots_reports_and_source_links(client, db, monkeypatch):
    from app.api import ingestion as api

    headers = authorize(monkeypatch)
    payload = {
        "id": ARTIST_ID,
        "name": "Spotify integration fixture",
        "genres": ["test-spotify-genre"],
        "albums": [
            {
                "id": ALBUM_ID,
                "title": "Spotify release fixture",
                "release_date": "2024-06",
                "tracks": [{"id": TRACK_ID, "title": "Spotify recording fixture", "position": 1}],
            }
        ],
        "metrics": {"followers": 0, "popularity": None},
    }

    class Provider:
        def fetch_artist(self, identifier):
            assert identifier == ARTIST_ID
            return payload

    monkeypatch.setattr(api, "get_spotify", lambda: Provider())
    save_artist(db, {"id": "hidden-demo-test", "name": "Hidden demo"}, "demo")
    response = client.post(
        "/api/v1/ingestion/spotify/artists",
        json={"artist_id": "https://open.spotify.com/artist/" + ARTIST_ID},
        headers=headers,
    )
    assert response.status_code == 201 and response.json()["provider"] == "spotify"
    data = client.get("/api/v1/artists/search").json()
    assert data["total"] == 1 and data["items"][0]["followers"] == 0
    assert data["items"][0]["sources"][0]["url"] == "https://open.spotify.com/artist/" + ARTIST_ID
    assert client.get("/api/v1/dashboard/overview").json()["demo_included"] is False
    assert client.get("/api/v1/analytics/genres").json()["items"] == [
        {"genre": "test-spotify-genre", "artists": 1}
    ]
    report = client.post("/api/v1/reports", json={"format": "csv"})
    assert "Spotify integration fixture" in report.text and "Hidden demo" not in report.text
    assert "https://open.spotify.com/artist/" + ARTIST_ID in report.text
    import io

    from pypdf import PdfReader

    pdf = client.post("/api/v1/reports", json={"format": "pdf"})
    assert pdf.status_code == 200
    pdf_text = " ".join(page.extract_text() for page in PdfReader(io.BytesIO(pdf.content)).pages)
    assert "open.spotify.com" in pdf_text and "Spotify integration fixture" in pdf_text

    assert (
        client.post(
            "/api/v1/ingestion/spotify/artists", json={"artist_id": ARTIST_ID}, headers=headers
        ).status_code
        == 429
    )
    assert db.scalar(select(func.count()).select_from(ArtistMetricSnapshot)) == 1


@pytest.mark.integration
def test_reimport_keeps_ids_and_clears_unavailable_old_metrics(db):
    payload = {
        "id": ARTIST_ID,
        "name": "Snapshot fixture",
        "metrics": {"followers": 100, "popularity": 20},
    }
    first = ingest(db, lambda: payload, "spotify")
    payload["metrics"] = {"followers": None, "popularity": None}
    second = ingest(db, lambda: payload, "spotify")
    assert first.id == second.id
    assert (
        db.scalar(
            select(func.count())
            .select_from(SourceMapping)
            .where(SourceMapping.provider == "spotify")
        )
        == 1
    )
    snapshots = list(
        db.scalars(select(ArtistMetricSnapshot).order_by(ArtistMetricSnapshot.captured_at))
    )
    assert len(snapshots) == 2 and snapshots[-1].followers is None


@pytest.mark.integration
def test_spotify_api_authorization_validation_and_missing_configuration(client, monkeypatch):
    from app.api.ingestion import get_spotify

    settings = get_settings()
    get_spotify.cache_clear()
    monkeypatch.setattr(settings, "ingestion_enabled", False)
    assert (
        client.post("/api/v1/ingestion/spotify/artists", json={"artist_id": ARTIST_ID}).status_code
        == 503
    )
    headers = authorize(monkeypatch)
    assert (
        client.post("/api/v1/ingestion/spotify/artists", json={"artist_id": ARTIST_ID}).status_code
        == 401
    )
    assert (
        client.post(
            "/api/v1/ingestion/spotify/artists",
            json={"artist_id": "https://evil.example/artist/" + ARTIST_ID},
            headers=headers,
        ).status_code
        == 422
    )
    monkeypatch.setattr(settings, "spotify_client_id", "")
    monkeypatch.setattr(settings, "spotify_client_secret", SecretStr(""))
    assert (
        client.post(
            "/api/v1/ingestion/spotify/artists", json={"artist_id": ARTIST_ID}, headers=headers
        ).status_code
        == 503
    )
    get_spotify.cache_clear()


@pytest.mark.integration
def test_spotify_upstream_rate_limit_audits_failure(client, db, monkeypatch):
    from app.api import ingestion as api

    headers = authorize(monkeypatch)

    class Provider:
        def fetch_artist(self, identifier):
            raise SpotifyError("Spotify rate limit reached", 429, 90)

    monkeypatch.setattr(api, "get_spotify", lambda: Provider())
    result = client.post(
        "/api/v1/ingestion/spotify/artists", json={"artist_id": ARTIST_ID}, headers=headers
    )
    assert result.status_code == 429 and result.headers["Retry-After"] == "90"
    assert (
        db.scalar(select(IngestionRun).where(IngestionRun.provider == "spotify")).status == "failed"
    )


@pytest.mark.parametrize("status", [400, 401])
def test_rejected_client_credentials_are_actionable_and_redacted(status):
    provider = spotify_client(
        lambda _: httpx.Response(status, json={"error": "private-secret-details"})
    )
    with pytest.raises(SpotifyError) as error:
        provider.fetch_artist(ARTIST_ID)
    assert error.value.status_code == 503
    assert "check the Developer app" in str(error.value)
    assert "private-secret-details" not in str(error.value)


def test_import_deadline_does_not_continue_after_slow_authorization():
    clock = [100.0]
    requests = []

    def handler(request):
        requests.append(request)
        clock[0] = 200.0
        return httpx.Response(200, json={"access_token": "offline-token", "expires_in": 3600})

    with (
        patch("app.providers.spotify.time.monotonic", side_effect=lambda: clock[0]),
        pytest.raises(SpotifyError, match="time budget"),
    ):
        spotify_client(handler).fetch_artist(ARTIST_ID)
    assert len(requests) == 1 and requests[0].url.host == "accounts.spotify.com"
