import copy
import json
import uuid
from unittest.mock import patch

import httpx
import pytest
from sqlalchemy import func, select

from app.models import Album, AlbumTrack, ArtistMetricSnapshot
from app.providers.spotify import Spotify, SpotifyError
from app.services import bulk_imports as bulk
from app.services.ingestion import save_artist

ARTIST = "Q" * 22


class Catalogue:
    def __init__(self, releases=12, first_tracks=53):
        self.releases = [
            {
                "id": "AL" + str(i).zfill(20),
                "name": f"Release fixture {i}",
                "album_type": ["album", "single", "compilation"][i % 3],
                "release_date": "2024",
                "album_group": ["album", "single", "compilation"][i % 3],
            }
            for i in range(releases)
        ]
        self.track_counts = {
            release["id"]: first_tracks if i == 0 else 2 for i, release in enumerate(self.releases)
        }
        self.requests = []
        self.failure = None

    def handler(self, request):
        self.requests.append(request)
        if request.url.host == "accounts.spotify.com":
            return httpx.Response(
                200, json={"access_token": "offline-discography-token", "expires_in": 3600}
            )
        assert request.url.host == "api.spotify.com"
        if request.url.path.endswith("/artists/" + ARTIST):
            return httpx.Response(200, json={"id": ARTIST, "name": "Discography test fixture"})
        offset = int(request.url.params["offset"])
        limit = int(request.url.params["limit"])
        assert limit == 10
        if request.url.path.endswith("/albums"):
            groups = request.url.params["include_groups"].split(",")
            all_rows = [release for release in self.releases if release["album_group"] in groups]
        else:
            album_id = request.url.path.split("/")[-2]
            if self.failure == (album_id, offset):
                return httpx.Response(503)
            index = int(album_id[2:])
            all_rows = [
                {
                    "id": "TR" + str(index).zfill(10) + str(i).zfill(10),
                    "name": f"Recording fixture {i}",
                    "disc_number": 1,
                    "track_number": i + 1,
                    "duration_ms": None,
                }
                for i in range(self.track_counts[album_id])
            ]
        rows = all_rows[offset : offset + limit]
        return httpx.Response(
            200,
            json={
                "items": rows,
                "next": "https://untrusted.example/next"
                if offset + limit < len(all_rows)
                else None,
                "total": len(all_rows),
            },
        )

    def client(self, market="ZA"):
        return Spotify(
            "offline-client",
            "offline-secret",
            market=market,
            transport=httpx.MockTransport(self.handler),
        )


def walk(provider, groups=None):
    state = None
    steps = []
    for _ in range(200):
        step = provider.fetch_discography_step(
            ARTIST, state, groups or ["album", "single", "compilation"]
        )
        steps.append(step)
        state = json.loads(json.dumps(step["checkpoint"]))
        if step["complete"]:
            return state, steps
    pytest.fail("Discography never completed")


def test_full_provider_pages_past_album_and_track_limits_without_following_next_urls():
    fixture = Catalogue()
    provider = fixture.client()
    assert provider.max_albums == 5 and provider.max_tracks == 50
    state, steps = walk(provider)
    assert state["phase"] == "done" and state["releases_imported"] == 12
    assert state["tracks_imported"] == 75
    offsets = [
        int(r.url.params["offset"]) for r in fixture.requests if r.url.path.endswith("/albums")
    ]
    assert offsets == [0, 10]
    first = fixture.releases[0]["id"]
    assert [
        int(r.url.params["offset"])
        for r in fixture.requests
        if f"/albums/{first}/tracks" in r.url.path
    ] == [0, 10, 20, 30, 40, 50]
    assert "offline-discography-token" not in json.dumps(state)
    assert all(r.url.host in {"accounts.spotify.com", "api.spotify.com"} for r in fixture.requests)
    assert any(
        step["payload"] and step["payload"].get("albums", [{}])[0].get("release_type") == "single"
        for step in steps[1:]
    )


def test_singles_only_and_saved_market_are_respected_across_client_restart():
    fixture = Catalogue(releases=18)
    client = fixture.client()
    initial = client.fetch_discography_step(ARTIST, None, ["single"])
    checkpoint = initial["checkpoint"]
    restarted = fixture.client(market="US")
    for _ in range(30):
        step = restarted.fetch_discography_step(
            ARTIST, json.loads(json.dumps(checkpoint)), ["album"]
        )
        checkpoint = step["checkpoint"]
        if step["complete"]:
            break
    assert checkpoint["phase"] == "done" and checkpoint["releases_imported"] == 6
    for request in fixture.requests:
        if "offset" in request.url.params:
            assert request.url.params["market"] == "ZA"
        if request.url.path.endswith("/albums"):
            assert request.url.params["include_groups"] == "single"


def test_non_advancing_pagination_is_an_error_not_false_completion():
    fixture = Catalogue()
    provider = fixture.client()
    state = provider.fetch_discography_step(ARTIST, None, ["album"])["checkpoint"]
    original = provider._get

    def empty_page(path, deadline, **params):
        return {"items": [], "next": "https://untrusted.example/loop"}

    provider._get = empty_page
    with pytest.raises(SpotifyError, match="did not advance"):
        provider.fetch_discography_step(ARTIST, state, ["album"])
    provider._get = original


@pytest.mark.integration
def test_full_queue_import_is_complete_and_page_commits_survive_reloads(db, monkeypatch):
    fixture = Catalogue()
    monkeypatch.setattr(bulk, "get_spotify", fixture.client)
    batch = bulk.create_batch(db, [ARTIST], "Full fixture", uuid.uuid4())
    batch_id = batch.id
    for _ in range(100):
        assert bulk.process_one(db)
        db.expunge_all()
        batch = bulk.load_batch(db, batch_id)
        if batch.status == "completed":
            break
    assert batch.status == "completed" and batch.items[0].status == "succeeded"
    assert batch.items[0].checkpoint["releases_imported"] == 12
    assert db.scalar(select(func.count()).select_from(Album)) == 12
    assert db.scalar(select(func.count()).select_from(AlbumTrack)) == 75
    assert db.scalar(select(func.count()).select_from(ArtistMetricSnapshot)) == 1
    view = bulk.batch_json(db, batch)
    assert view["import_mode"] == "full" and view["items"][0]["progress"]["tracks_imported"] == 75


@pytest.mark.integration
def test_failed_page_retries_resume_and_old_track_positions_remain_until_album_finishes(
    db, monkeypatch
):
    fixture = Catalogue(releases=1)
    album_id = fixture.releases[0]["id"]
    save_artist(
        db,
        {
            "id": ARTIST,
            "name": "Previous metadata",
            "albums": [
                {
                    "id": album_id,
                    "title": "Existing release",
                    "tracks": [{"id": "Z" * 22, "title": "Previous position", "position": 99}],
                }
            ],
        },
        "spotify",
    )
    db.commit()
    provider = fixture.client()
    monkeypatch.setattr(bulk, "get_spotify", lambda: provider)
    batch = bulk.create_batch(db, [ARTIST], "Resume fixture", uuid.uuid4())
    for _ in range(3):
        assert bulk.process_one(db)  # artist, release page, first ten tracks
    item = bulk.load_batch(db, batch.id, refresh=True).items[0]
    assert item.checkpoint["track_offset"] == 10
    assert db.scalar(select(AlbumTrack).where(AlbumTrack.position == 99)) is not None
    fixture.failure = (album_id, 10)
    with patch("app.providers.spotify.time.sleep"):
        assert bulk.process_one(db)
    item = bulk.load_batch(db, batch.id, refresh=True).items[0]
    assert item.status == "failed" and item.checkpoint["track_offset"] == 10
    assert db.scalar(select(func.count()).select_from(AlbumTrack)) == 11
    fixture.failure = None
    bulk.change_batch(db, batch.id, "retry")
    for _ in range(20):
        assert bulk.process_one(db)
        batch = bulk.load_batch(db, batch.id, refresh=True)
        if batch.status == "completed":
            break
    assert batch.items[0].status == "succeeded"
    assert db.scalar(select(func.count()).select_from(AlbumTrack)) == 53
    assert db.scalar(select(AlbumTrack).where(AlbumTrack.position == 99)) is None
    assert db.scalar(select(func.count()).select_from(ArtistMetricSnapshot)) == 1
    # The first track page was committed and never requested a second time.
    assert (
        sum(
            r.url.path.endswith(f"/{album_id}/tracks") and r.url.params.get("offset") == "0"
            for r in fixture.requests
        )
        == 1
    )


@pytest.mark.integration
def test_page_data_and_checkpoint_rollback_together_on_finalization_error(db, monkeypatch):
    fixture = Catalogue(releases=1, first_tracks=12)
    monkeypatch.setattr(bulk, "get_spotify", fixture.client)
    batch = bulk.create_batch(db, [ARTIST], "Atomic fixture", uuid.uuid4())
    assert bulk.process_one(db) and bulk.process_one(db)
    item = bulk.load_batch(db, batch.id, refresh=True).items[0]
    before = copy.deepcopy(item.checkpoint)
    # Fail after saving the track payload but before the worker commits its checkpoint.
    original = bulk.load_batch

    def fail_finalize(*args, **kwargs):
        if kwargs.get("lock"):
            raise RuntimeError("test-only finalization failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(bulk, "load_batch", fail_finalize)
    with pytest.raises(RuntimeError, match="test-only"):
        bulk.process_one(db)
    db.rollback()
    monkeypatch.setattr(bulk, "load_batch", original)
    item = bulk.load_batch(db, batch.id, refresh=True).items[0]
    assert item.checkpoint == before
    assert db.scalar(select(func.count()).select_from(AlbumTrack)) == 0


@pytest.mark.integration
def test_full_queue_api_exposes_scope_and_rejects_empty_release_types(client, monkeypatch):
    from app.api import bulk_imports as api
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "ingestion_enabled", True)
    monkeypatch.setattr(settings, "ingestion_token", "offline-token-" + "x" * 32)
    monkeypatch.setattr(api, "get_spotify", lambda: object())
    headers = {"Authorization": "Bearer " + settings.ingestion_token}
    assert (
        client.get("/api/v1/ingestion/spotify/batches/access", headers=headers).json()[
            "full_discography"
        ]
        is True
    )
    body = {"request_id": str(uuid.uuid4()), "artist_ids": [ARTIST], "release_types": ["single"]}
    response = client.post("/api/v1/ingestion/spotify/batches", headers=headers, json=body)
    assert response.status_code == 202 and response.json()["release_types"] == ["single"]
    assert response.json()["import_mode"] == "full"
    for groups in [[], ["unknown"]]:
        assert (
            client.post(
                "/api/v1/ingestion/spotify/batches",
                headers=headers,
                json={**body, "release_types": groups},
            ).status_code
            == 422
        )
    assert (
        client.post(
            "/api/v1/ingestion/spotify/batches",
            headers=headers,
            json={**body, "release_types": ["album"]},
        ).status_code
        == 409
    )


@pytest.mark.integration
def test_full_page_backoff_is_durable_even_after_many_successful_steps(db, monkeypatch):
    from datetime import UTC, datetime

    from app.services.import_control import next_import_at

    fixture = Catalogue(releases=1, first_tracks=90)
    provider = fixture.client()
    monkeypatch.setattr(bulk, "get_spotify", lambda: provider)
    batch = bulk.create_batch(db, [ARTIST], "Backoff fixture", uuid.uuid4())
    for _ in range(8):
        assert bulk.process_one(db)
    before = copy.deepcopy(bulk.load_batch(db, batch.id, refresh=True).items[0].checkpoint)
    with patch.object(
        provider,
        "fetch_discography_step",
        side_effect=SpotifyError("Spotify rate limit", 429, 120),
    ):
        assert bulk.process_one(db)
    item = bulk.load_batch(db, batch.id, refresh=True).items[0]
    assert item.status == "pending" and item.rate_limit_attempts == 1
    assert item.checkpoint == before and item.attempts == 9
    assert next_import_at(db, continuation=True) > datetime.now(UTC)
    assert not bulk.process_one(db)
