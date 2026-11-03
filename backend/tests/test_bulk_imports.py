import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text, update

from app.core.config import get_settings
from app.core.database import engine
from app.models import IngestionRun, SpotifyImportBatch
from app.providers.spotify import SpotifyError
from app.services import bulk_imports as bulk

IDS = [letter * 22 for letter in "ABCDE"]
pytestmark = pytest.mark.integration


@pytest.fixture
def operator(client, monkeypatch):
    from app.api import bulk_imports as api

    settings = get_settings()
    monkeypatch.setattr(settings, "ingestion_enabled", True)
    monkeypatch.setattr(settings, "ingestion_token", "offline-test-" + "x" * 32)
    monkeypatch.setattr(settings, "bulk_worker_enabled", True)
    monkeypatch.setattr(api, "get_spotify", lambda: object())
    return {"Authorization": "Bearer " + settings.ingestion_token}


@pytest.fixture
def provider(monkeypatch):
    class FakeSpotify:
        calls = []
        error = None

        def fetch_artist(self, identifier):
            self.calls.append(identifier)
            if self.error is not None:
                raise self.error
            return {
                "id": identifier,
                "name": "Queue test fixture " + identifier[0],
                "metrics": {"followers": None, "popularity": None},
            }

    fake = FakeSpotify()
    monkeypatch.setattr(bulk, "get_spotify", lambda: fake)
    return fake


def create(db, ids=IDS[:2]):
    return bulk.create_batch(db, ids, "Queue test", uuid.uuid4(), import_mode="limited")


def clear_cooldown(db):
    db.execute(
        update(IngestionRun).values(
            started_at=datetime.now(UTC) - timedelta(seconds=180), retry_after_at=None
        )
    )
    db.commit()


def test_batch_api_auth_validation_dedup_and_idempotency(client, operator):
    body = {
        "request_id": str(uuid.uuid4()),
        "artist_ids": [
            IDS[0],
            "spotify:artist:" + IDS[0],
            "https://open.spotify.com/artist/" + IDS[1] + "?si=share",
        ],
    }
    assert client.post("/api/v1/ingestion/spotify/batches", json=body).status_code == 401
    response = client.post("/api/v1/ingestion/spotify/batches", json=body, headers=operator)
    assert response.status_code == 202 and response.headers["Cache-Control"] == "no-store"
    batch = response.json()
    assert client.post(f"/api/v1/ingestion/spotify/batches/{batch['id']}/cancel").status_code == 401
    assert batch["total"] == 2 and batch["counts"]["pending"] == 2
    again = client.post("/api/v1/ingestion/spotify/batches", json=body, headers=operator)
    assert again.json()["id"] == batch["id"]
    other = {**body, "artist_ids": [IDS[2]]}
    assert (
        client.post("/api/v1/ingestion/spotify/batches", json=other, headers=operator).status_code
        == 409
    )
    for ids in [[], ["https://evil.example/artist/" + IDS[0]], [IDS[0]] * 101]:
        assert (
            client.post(
                "/api/v1/ingestion/spotify/batches",
                json={"request_id": str(uuid.uuid4()), "artist_ids": ids},
                headers=operator,
            ).status_code
            == 422
        )
    assert client.get(f"/api/v1/ingestion/spotify/batches/{batch['id']}").status_code == 401
    assert (
        client.get(f"/api/v1/ingestion/spotify/batches/{batch['id']}", headers=operator).json()[
            "total"
        ]
        == 2
    )


def test_disabled_worker_and_invalid_credentials_cannot_enqueue(client, operator, monkeypatch):
    from app.api import bulk_imports as api

    monkeypatch.setattr(get_settings(), "bulk_worker_enabled", False)
    assert (
        client.get("/api/v1/ingestion/spotify/batches/access", headers=operator).status_code == 503
    )
    monkeypatch.setattr(get_settings(), "bulk_worker_enabled", True)

    def unavailable():
        raise SpotifyError("Configure Spotify client credentials on the API server", 503)

    monkeypatch.setattr(api, "get_spotify", unavailable)
    assert (
        client.post(
            "/api/v1/ingestion/spotify/batches",
            headers=operator,
            json={"request_id": str(uuid.uuid4()), "artist_ids": [IDS[0]]},
        ).status_code
        == 503
    )


def test_queue_imports_one_at_a_time_and_respects_existing_cooldown(db, provider):
    batch = create(db)
    assert bulk.process_one(db)
    view = bulk.batch_json(db, bulk.load_batch(db, batch.id, refresh=True))
    assert view["counts"] == {
        "pending": 1,
        "running": 0,
        "succeeded": 1,
        "failed": 0,
        "cancelled": 0,
    }
    assert not bulk.process_one(db) and provider.calls == [IDS[0]]
    clear_cooldown(db)
    assert bulk.process_one(db)
    db.expire_all()
    view = bulk.batch_json(db, bulk.load_batch(db, batch.id, refresh=True))
    assert view["status"] == "completed" and view["counts"]["succeeded"] == 2
    assert provider.calls == IDS[:2]


def test_queue_is_durable_across_session_identity_map_reset(db, provider):
    batch = create(db, [IDS[0]])
    batch_id = batch.id
    db.expunge_all()
    assert bulk.process_one(db)
    db.expunge_all()
    batch = bulk.load_batch(db, batch_id)
    assert batch.status == "completed" and batch.items[0].artist_id is not None


def test_pause_resume_and_cancel_do_not_reimport_successful_items(db, provider):
    batch = create(db, IDS[:3])
    bulk.change_batch(db, batch.id, "pause")
    assert not bulk.process_one(db) and not provider.calls
    bulk.change_batch(db, batch.id, "resume")
    assert bulk.process_one(db)
    bulk.change_batch(db, batch.id, "cancel")
    batch = bulk.load_batch(db, batch.id, refresh=True)
    assert batch.status == "cancelled"
    assert [i.status for i in batch.items] == ["succeeded", "cancelled", "cancelled"]
    with pytest.raises(Exception) as error:
        bulk.change_batch(db, batch.id, "retry")
    assert error.value.status_code == 409


def test_retry_failed_only_and_keep_successful_artist(db, provider):
    batch = create(db)
    assert bulk.process_one(db)
    clear_cooldown(db)
    provider.error = SpotifyError("Artist unavailable", 404)
    assert bulk.process_one(db)
    batch = bulk.load_batch(db, batch.id, refresh=True)
    assert batch.status == "completed" and [i.status for i in batch.items] == [
        "succeeded",
        "failed",
    ]
    first_id = batch.items[0].artist_id
    bulk.change_batch(db, batch.id, "retry")
    provider.error = None
    clear_cooldown(db)
    assert bulk.process_one(db)
    batch = bulk.load_batch(db, batch.id, refresh=True)
    assert batch.items[0].artist_id == first_id and batch.status == "completed"
    assert provider.calls == [IDS[0], IDS[1], IDS[1]]


def test_spotify_rate_limit_is_persisted_and_blocks_all_imports(db, provider):
    from app.services.import_control import import_slot

    batch = create(db)
    provider.error = SpotifyError("Spotify rate limit reached", 429, 180)
    assert bulk.process_one(db)
    batch = bulk.load_batch(db, batch.id, refresh=True)
    assert batch.items[0].status == "pending" and batch.items[0].last_http_status == 429
    run = db.scalar(select(IngestionRun).where(IngestionRun.provider == "spotify"))
    assert (run.retry_after_at - datetime.now(UTC)).total_seconds() > 170
    assert not bulk.process_one(db) and len(provider.calls) == 1
    with pytest.raises(Exception) as error:
        with import_slot(db, "spotify"):
            pytest.fail("Backoff must block manual imports too")
    assert error.value.status_code == 429 and int(error.value.headers["Retry-After"]) > 170


def test_access_failure_pauses_batch_instead_of_failing_every_artist(db, provider):
    batch = create(db)
    provider.error = SpotifyError("Spotify denied app access", 403)
    assert bulk.process_one(db)
    batch = bulk.load_batch(db, batch.id, refresh=True)
    assert batch.status == "paused" and [i.status for i in batch.items] == ["failed", "pending"]
    assert not bulk.process_one(db) and len(provider.calls) == 1


def test_abandoned_claim_is_recovered_after_lease_expiry(db, provider):
    batch = create(db, [IDS[0]])
    item = batch.items[0]
    item.status = "running"
    item.lease_until = datetime.now(UTC) - timedelta(seconds=1)
    item.attempts = 1
    db.commit()
    assert bulk.process_one(db)
    batch = bulk.load_batch(db, batch.id, refresh=True)
    assert batch.items[0].status == "succeeded" and batch.items[0].attempts == 2


def test_live_claim_is_not_stolen(db, provider):
    batch = create(db, [IDS[0]])
    batch.items[0].status = "running"
    batch.items[0].lease_until = datetime.now(UTC) + timedelta(seconds=120)
    db.commit()
    assert not bulk.process_one(db) and not provider.calls


def test_coordinator_and_manual_import_locks_are_respected(db, provider):
    batch = create(db, [IDS[0]])
    with engine.connect() as lock:
        lock.execute(text("SELECT pg_advisory_lock(824019)"))
        try:
            assert not bulk.process_one(db)
        finally:
            lock.execute(text("SELECT pg_advisory_unlock(824019)"))
    with engine.connect() as lock:
        lock.execute(text("SELECT pg_advisory_lock(824017)"))
        try:
            assert bulk.process_one(db)
        finally:
            lock.execute(text("SELECT pg_advisory_unlock(824017)"))
    batch = bulk.load_batch(db, batch.id, refresh=True)
    assert batch.items[0].status == "pending" and batch.items[0].attempts == 0
    assert not provider.calls


def test_unexpected_errors_do_not_leak_sensitive_details(db, monkeypatch):
    batch = create(db, [IDS[0]])
    monkeypatch.setattr(bulk, "get_spotify", lambda: object())

    def broken(*args):
        raise RuntimeError("private diagnostic secret")

    monkeypatch.setattr(bulk, "perform_spotify_import", broken)
    assert bulk.process_one(db)
    view = bulk.batch_json(db, bulk.load_batch(db, batch.id, refresh=True))
    assert view["counts"]["failed"] == 1 and "private" not in str(view)


def test_active_batch_limit(db):
    for _ in range(10):
        create(db, [IDS[0]])
    with pytest.raises(Exception) as error:
        create(db, [IDS[0]])
    assert error.value.status_code == 409
    assert len(list(db.scalars(select(SpotifyImportBatch)))) == 10


def test_worker_loop_stops_cleanly(monkeypatch):
    calls = []
    monkeypatch.setattr(bulk, "tick", lambda: calls.append(True))

    async def exercise():
        stop = asyncio.Event()
        task = asyncio.create_task(bulk.run_worker(stop))
        for _ in range(100):
            if calls:
                break
            await asyncio.sleep(0.01)
        stop.set()
        await asyncio.wait_for(task, 2)

    asyncio.run(exercise())
    assert calls


def test_cancellation_during_a_request_keeps_success_and_cancels_only_remaining(db, monkeypatch):
    batch = create(db)

    class Provider:
        def fetch_artist(self, identifier):
            # Interleave an operator cancellation before the in-flight import finishes.
            bulk.change_batch(db, batch.id, "cancel")
            return {"id": identifier, "name": "Cancelled-flight fixture"}

    monkeypatch.setattr(bulk, "get_spotify", lambda: Provider())
    assert bulk.process_one(db)
    batch = bulk.load_batch(db, batch.id, refresh=True)
    assert batch.status == "cancelled"
    assert [item.status for item in batch.items] == ["succeeded", "cancelled"]
    assert batch.items[0].artist_id is not None
    clear_cooldown(db)
    assert not bulk.process_one(db)


def test_repeated_rate_limits_pause_remaining_queue_for_review(db, provider):
    batch = create(db)
    provider.error = SpotifyError("Spotify rate limit reached", 429, 60)
    for attempt in range(5):
        assert bulk.process_one(db)
        if attempt < 4:
            clear_cooldown(db)
            batch = bulk.load_batch(db, batch.id, refresh=True)
            batch.items[0].available_at = datetime.now(UTC) - timedelta(seconds=1)
            db.commit()
    batch = bulk.load_batch(db, batch.id, refresh=True)
    assert batch.status == "paused"
    assert [item.status for item in batch.items] == ["failed", "pending"]
    assert provider.calls == [IDS[0]] * 5
