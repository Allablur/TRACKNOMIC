import logging

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.ingestion import router as ingestion_router
from app.api.reports import router as report_router
from app.api.routes import router
from app.core.config import get_settings
from app.core.database import engine
from app.core.middleware import RequestGuard

logger = logging.getLogger(__name__)
app = FastAPI(title="Trackonomics API", version="0.1.0")
app.include_router(router)
app.include_router(report_router)
app.include_router(ingestion_router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.add_middleware(TrustedHostMiddleware, allowed_hosts=get_settings().allowed_hosts)
app.add_middleware(RequestGuard, max_bytes=get_settings().max_request_bytes)


class HealthResponse(BaseModel):
    status: str
    database: str


def check_database() -> None:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))


@app.get("/health", response_model=HealthResponse, tags=["health"])
def health() -> HealthResponse:
    """Readiness includes a real database query; unavailable databases return 503."""
    try:
        check_database()
    except SQLAlchemyError:
        logger.warning("Database readiness check failed")
        raise HTTPException(status_code=503, detail="Database unavailable") from None
    return HealthResponse(status="ok", database="connected")
