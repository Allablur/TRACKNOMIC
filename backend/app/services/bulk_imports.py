"""Durable single-artist queue; PostgreSQL locks coordinate API processes."""

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.database import SessionLocal, engine
from app.models import SpotifyImportBatch, SpotifyImportItem
from app.providers.spotify import SpotifyError
from app.services.import_control import next_import_at
from app.services.spotify_import import (
    get_spotify,
    perform_discography_step,
    perform_spotify_import,
)

logger = logging.getLogger(__name__)
TERMINAL = {"succeeded", "failed", "cancelled"}


def load_batch(db, batch_id, refresh=False, lock=False):
    statement = (
        select(SpotifyImportBatch)
        .where(SpotifyImportBatch.id == batch_id)
        .options(selectinload(SpotifyImportBatch.items))
    )
    if lock:
        statement = statement.with_for_update()
    if refresh:
        statement = statement.execution_options(populate_existing=True)
    batch = db.scalar(statement)
    if batch is None:
        raise HTTPException(404, "Import batch not found")
    return batch


def settle(batch):
    if batch.status in {"active", "paused"} and all(i.status in TERMINAL for i in batch.items):
        batch.status = "completed"
    batch.updated_at = datetime.now(UTC)


def batch_json(db, batch):
    now = datetime.now(UTC)
    counts = {
        status: sum(i.status == status for i in batch.items)
        for status in ["pending", "running", "succeeded", "failed", "cancelled"]
    }
    pending = [
        max(i.available_at, next_import_at(db, continuation=bool(i.checkpoint)))
        for i in batch.items
        if i.status == "pending"
    ]
    eligible = min(pending) if pending else None
    return {
        "id": str(batch.id),
        "name": batch.name,
        "import_mode": batch.import_mode,
        "release_types": batch.release_types,
        "status": batch.status,
        "created_at": batch.created_at.isoformat(),
        "server_time": now.isoformat(),
        "next_attempt_at": eligible.isoformat() if eligible and batch.status == "active" else None,
        "worker_enabled": get_settings().bulk_worker_enabled,
        "total": len(batch.items),
        "counts": counts,
        "items": [
            {
                "id": str(i.id),
                "spotify_id": i.spotify_id,
                "position": i.position,
                "status": i.status,
                "attempts": i.attempts,
                "name": i.artist_name,
                "artist_id": str(i.artist_id) if i.artist_id else None,
                "error": i.error,
                "available_at": i.available_at.isoformat(),
                "last_http_status": i.last_http_status,
                "progress": {
                    "phase": i.checkpoint.get("phase"),
                    "releases_imported": i.checkpoint.get("releases_imported", 0),
                    "tracks_imported": i.checkpoint.get("tracks_imported", 0),
                }
                if i.checkpoint
                else None,
            }
            for i in batch.items
        ],
    }


def create_batch(db, artist_ids, name, request_id, import_mode="full", release_types=None):
    release_types = release_types or (
        ["album", "single"] if import_mode == "limited" else ["album", "single", "compilation"]
    )
    # Keep creation bounded even if multiple authenticated requests arrive together.
    db.execute(text("SELECT pg_advisory_xact_lock(824020)"))
    existing = db.scalar(
        select(SpotifyImportBatch).where(SpotifyImportBatch.request_id == request_id)
    )
    if existing is not None:
        existing = load_batch(db, existing.id)
        if (
            [item.spotify_id for item in existing.items] != artist_ids
            or existing.name != name
            or existing.import_mode != import_mode
            or existing.release_types != release_types
        ):
            raise HTTPException(409, "This request ID was already used for a different artist list")
        return existing
    active = db.scalar(
        select(func.count())
        .select_from(SpotifyImportBatch)
        .where(SpotifyImportBatch.status.in_(["active", "paused"]))
    )
    if active >= 10:
        raise HTTPException(409, "Finish or cancel an existing batch before creating another")
    batch = SpotifyImportBatch(
        request_id=request_id,
        import_mode=import_mode,
        release_types=release_types,
        name=name,
        items=[
            SpotifyImportItem(spotify_id=id, position=position)
            for position, id in enumerate(artist_ids, 1)
        ],
    )
    db.add(batch)
    db.commit()
    return load_batch(db, batch.id, refresh=True)


def change_batch(db, batch_id, action):
    batch = load_batch(db, batch_id, refresh=True, lock=True)
    if action == "pause" and batch.status == "active":
        batch.status = "paused"
    elif action == "resume" and batch.status == "paused":
        batch.status = "active"
    elif action == "cancel" and batch.status != "completed":
        batch.status = "cancelled"
        for item in batch.items:
            if item.status in {"pending", "running"}:
                item.status, item.error, item.lease_until = "cancelled", None, None
                item.completed_at = datetime.now(UTC)
    elif action == "retry":
        if batch.status == "cancelled":
            raise HTTPException(409, "A cancelled batch cannot be restarted; create a new batch")
        for item in batch.items:
            if item.status == "failed":
                item.status, item.error, item.last_http_status = "pending", None, None
                item.attempts, item.available_at, item.completed_at = 0, datetime.now(UTC), None
                item.rate_limit_attempts = 0
        batch.status = "active"
    settle(batch)
    db.commit()
    return load_batch(db, batch_id, refresh=True)


def process_one(db):
    # Session advisory lock is held over claim/import/finalization, across all workers.
    with engine.connect() as coordinator:
        if not coordinator.scalar(text("SELECT pg_try_advisory_lock(824019)")):
            return False
        try:
            return _process_one(db)
        finally:
            coordinator.execute(text("SELECT pg_advisory_unlock(824019)"))


def _process_one(db):
    now = datetime.now(UTC)
    item = db.scalar(
        select(SpotifyImportItem)
        .join(SpotifyImportBatch)
        .where(
            SpotifyImportBatch.status == "active",
            or_(
                and_(SpotifyImportItem.status == "pending", SpotifyImportItem.available_at <= now),
                and_(SpotifyImportItem.status == "running", SpotifyImportItem.lease_until < now),
            ),
        )
        .order_by(SpotifyImportBatch.created_at, SpotifyImportItem.position)
        .with_for_update(of=SpotifyImportItem, skip_locked=True)
        .limit(1)
    )
    if item is None:
        return False
    if next_import_at(db, continuation=bool(item.checkpoint)) > datetime.now(UTC):
        db.rollback()
        return False
    mode = db.get(SpotifyImportBatch, item.batch_id).import_mode
    groups = db.get(SpotifyImportBatch, item.batch_id).release_types
    item.status, item.lease_until = "running", now + timedelta(seconds=120)
    item.attempts += 1
    item_id, batch_id, identifier = item.id, item.batch_id, item.spotify_id
    db.commit()
    result, failure = None, None
    try:
        if mode == "full":
            result = perform_discography_step(
                db, identifier, get_spotify(), item.checkpoint, groups
            )
        else:
            result = perform_spotify_import(db, identifier, get_spotify())
    except (SpotifyError, HTTPException) as exc:
        failure = exc
        db.rollback()
    except Exception:
        # Keep credentials, response bodies and database connection details out of errors.
        logger.warning("Bulk import failed unexpectedly for batch=%s item=%s", batch_id, item_id)
        failure = SpotifyError("Import interrupted; retry this artist after checking the API")
        db.rollback()
    # Refresh because pause/cancel can arrive while a provider request is in flight.
    batch = load_batch(db, batch_id, refresh=True, lock=True)
    item = next(i for i in batch.items if i.id == item_id)
    item.lease_until = None
    if result is not None:
        complete = result.get("complete", True)
        item.error, item.last_http_status, item.rate_limit_attempts = (
            None,
            201 if complete else 202,
            0,
        )
        item.artist_id, item.artist_name = UUID(result["id"]), result["name"]
        if "checkpoint" in result:
            item.checkpoint = result["checkpoint"]
        if complete:
            item.status, item.completed_at = "succeeded", datetime.now(UTC)
        elif batch.status != "cancelled":
            item.status, item.available_at, item.completed_at = "pending", datetime.now(UTC), None
    else:
        status = failure.status_code
        detail = str(failure) if isinstance(failure, SpotifyError) else str(failure.detail)
        if status == 429 and isinstance(failure, SpotifyError):
            item.rate_limit_attempts += 1
        if status == 429 and batch.status != "cancelled" and item.rate_limit_attempts < 5:
            headers = getattr(failure, "headers", None) or {}
            retry = getattr(failure, "retry_after", None) or int(headers.get("Retry-After", "60"))
            item.status, item.error, item.last_http_status = "pending", detail, 429
            item.available_at = datetime.now(UTC) + timedelta(seconds=max(1, retry))
            # Waiting for an existing import/cooldown is not a provider attempt.
            if isinstance(failure, HTTPException):
                item.attempts -= 1
        elif batch.status != "cancelled":
            item.status, item.error, item.last_http_status = "failed", detail, status
            item.completed_at = datetime.now(UTC)
            if status in {403, 503, 429}:
                batch.status = "paused"
    settle(batch)
    db.commit()
    return True


def tick():
    with SessionLocal() as db:
        return process_one(db)


async def run_worker(stop: asyncio.Event):
    while not stop.is_set():
        try:
            await asyncio.to_thread(tick)
        except Exception:
            logger.warning("Bulk import worker unavailable; queued work will be retried")
        try:
            await asyncio.wait_for(stop.wait(), timeout=get_settings().bulk_poll_seconds)
        except TimeoutError:
            pass
