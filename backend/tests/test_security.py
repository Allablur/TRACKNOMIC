import uuid
from unittest.mock import patch

import pytest
from pydantic import ValidationError
from sqlalchemy import event, text

from app.core.config import Settings, get_settings
from app.core.database import engine
from app.services.ingestion import save_artist

pytestmark = pytest.mark.integration


def test_body_limit_headers_and_host_validation(client):
    response = client.post("/api/v1/reports", content=b"x" * 9000)
    assert response.status_code == 413
    assert response.headers["x-content-type-options"] == "nosniff"
    assert len(response.headers["x-request-id"]) == 32
    assert client.get("/health", headers={"Host": "evil.example"}).status_code == 400
    response = client.options(
        "/api/v1/reports",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"},
    )
    assert "access-control-allow-origin" not in response.headers


def test_enabled_ingestion_requires_secure_configuration():
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            ingestion_enabled=True,
            ingestion_token="short",
            musicbrainz_user_agent="Test/1",
        )


def test_authorized_import_cooldown_and_global_lock(client, monkeypatch):
    settings = get_settings()
    token = "test-" + "x" * 32
    monkeypatch.setattr(settings, "ingestion_enabled", True)
    monkeypatch.setattr(settings, "ingestion_token", token)
    monkeypatch.setattr(settings, "musicbrainz_user_agent", "Trackonomics-test/1 (offline tests)")
    headers = {"Authorization": "Bearer " + token}
    body = {"artist_mbid": str(uuid.uuid4())}
    with engine.connect() as lock:
        lock.execute(text("SELECT pg_advisory_lock(824017)"))
        try:
            assert (
                client.post("/api/v1/ingestion/artists", json=body, headers=headers).status_code
                == 429
            )
        finally:
            lock.execute(text("SELECT pg_advisory_unlock(824017)"))
    with patch(
        "app.api.ingestion.MusicBrainz.fetch_artist",
        return_value={"id": "secure-import-test", "name": "Secure import test"},
    ):
        response = client.post("/api/v1/ingestion/artists", json=body, headers=headers)
        assert response.status_code == 201
        assert "token" not in response.text
        response = client.post("/api/v1/ingestion/artists", json=body, headers=headers)
        assert response.status_code == 429 and response.headers["Retry-After"] == "60"


def test_report_concurrency_is_bounded(client):
    with engine.connect() as lock:
        lock.execute(text("SELECT pg_advisory_lock(824018)"))
        try:
            assert client.post("/api/v1/reports", json={"format": "pdf"}).status_code == 429
        finally:
            lock.execute(text("SELECT pg_advisory_unlock(824018)"))


def test_search_query_budget_is_constant(client, db):
    for i in range(25):
        save_artist(
            db,
            {
                "id": f"perf-{i}",
                "name": f"Performance fixture {i}",
                "genres": ["perf-genre"],
                "albums": [{"id": f"perf-album-{i}", "title": "Performance album"}],
            },
            "test",
        )
    counts = []
    for limit in [1, 20]:
        db.expunge_all()
        statements = []

        def capture(*args, target=statements):
            target.append(args[2])

        event.listen(engine, "before_cursor_execute", capture)
        try:
            response = client.get(
                "/api/v1/artists/search", params={"q": "Performance fixture", "limit": limit}
            )
            assert response.status_code == 200 and len(response.json()["items"]) == limit
        finally:
            event.remove(engine, "before_cursor_execute", capture)
        counts.append(len(statements))
    assert counts[0] == counts[1] and counts[1] <= 8, counts


def test_streamed_body_limit(client):
    def chunks():
        yield b"x" * 4096
        yield b"y" * 4097

    assert client.post("/api/v1/reports", content=chunks()).status_code == 413
