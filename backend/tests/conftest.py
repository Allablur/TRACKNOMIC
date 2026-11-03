import pytest
from sqlalchemy.orm import Session

from app.core.database import engine


@pytest.fixture
def db():
    # Every test is rolled back, including application commits via savepoints.
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
            yield session
        transaction.rollback()


@pytest.fixture
def client(db):
    from fastapi.testclient import TestClient

    from app.api.dependencies import get_db
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
