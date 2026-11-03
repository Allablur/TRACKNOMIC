from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.main import app

client = TestClient(app)


def test_health_reports_database_connection():
    with patch("app.main.check_database") as check:
        response = client.get("/health")
    check.assert_called_once()
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "connected"}


def test_health_returns_503_without_leaking_database_errors():
    error = OperationalError("SELECT 1", {}, Exception("sensitive connection details"))
    with patch("app.main.check_database", side_effect=error):
        response = client.get("/health")
    assert response.status_code == 503
    assert response.json() == {"detail": "Database unavailable"}


@pytest.mark.integration
def test_health_against_postgres():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["database"] == "connected"
