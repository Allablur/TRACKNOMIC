from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.analytics.catalogue import (
    Provider,
    artist_options,
    artist_scope,
    artists_json,
    genres,
    overview,
    releases,
)
from app.api.dependencies import get_db
from app.core.database import engine
from app.models import Artist
from app.services.reports import csv_report, pdf_report

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])


class ReportRequest(BaseModel):
    format: Literal["csv", "pdf"] = "csv"
    provider: Provider = "spotify"
    q: str = Field(default="", max_length=150)
    country: str = Field(default="", max_length=3)


def generate_report(body: ReportRequest, db: Session):
    filters = body.model_dump(exclude={"format"})
    statement = artist_scope(**filters)
    count = db.scalar(select(func.count()).select_from(statement.subquery()))
    # Avoid silently truncated exports and unbounded synchronous PDF generation.
    cap = 500 if body.format == "pdf" else 10000
    if count > cap:
        raise HTTPException(413, f"Narrow filters to at most {cap} artists for this format")
    items = db.scalars(statement.options(*artist_options()).order_by(Artist.name, Artist.id)).all()
    artists = artists_json(db, list(items))
    if body.format == "csv":
        data, media = csv_report(artists, filters), "text/csv; charset=utf-8"
    else:
        data = pdf_report(
            artists,
            filters,
            overview(db, **filters),
            genres(db, **filters),
            releases(db, **filters),
        )
        media = "application/pdf"
    return Response(
        data,
        media_type=media,
        headers={
            "Content-Disposition": f'attachment; filename="trackonomics-catalogue.{body.format}"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("")
def report(body: ReportRequest, db: Annotated[Session, Depends(get_db)]):
    with engine.connect() as lock:
        if not lock.scalar(text("SELECT pg_try_advisory_lock(824018)")):
            raise HTTPException(
                429, "Another report is running; retry shortly", headers={"Retry-After": "5"}
            )
        try:
            return generate_report(body, db)
        finally:
            lock.execute(text("SELECT pg_advisory_unlock(824018)"))
