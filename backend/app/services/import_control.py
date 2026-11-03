import math
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.database import engine
from app.models import IngestionRun


def next_import_at(db: Session, provider="spotify", continuation=False) -> datetime:
    latest, retry = db.execute(
        select(func.max(IngestionRun.started_at), func.max(IngestionRun.retry_after_at)).where(
            IngestionRun.provider == provider
        )
    ).one()
    now = datetime.now(UTC)
    return max(
        now, latest + timedelta(seconds=60) if latest and not continuation else now, retry or now
    )


@contextmanager
def import_slot(db: Session, provider: str, continuation=False):
    with engine.connect() as lock:
        if not lock.scalar(text("SELECT pg_try_advisory_lock(824017)")):
            raise HTTPException(429, "Another import is running", headers={"Retry-After": "5"})
        try:
            wait = math.ceil(
                (
                    next_import_at(db, provider, continuation=continuation) - datetime.now(UTC)
                ).total_seconds()
            )
            if wait > 0:
                raise HTTPException(
                    429, "Import cooldown is active", headers={"Retry-After": str(wait)}
                )
            yield
        finally:
            lock.execute(text("SELECT pg_advisory_unlock(824017)"))
