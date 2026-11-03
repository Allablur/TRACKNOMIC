import logging

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.core.database import engine

logger = logging.getLogger(__name__)
app = FastAPI(title="Trackonomics API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_methods=["GET"],
    allow_headers=["*"],
)


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
