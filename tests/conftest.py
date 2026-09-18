import os

# Must be set before the app is imported: settings are read at import time
os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/taskboard_test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")

import pytest
import redis
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.core.config import settings
from app.db.session import engine
from app.main import app

TABLES = "users, boards, board_members, lists, tasks"


def _ensure_test_database_exists(url):
    admin_engine = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        exists = conn.execute(text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": url.database}).scalar()
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{url.database}"'))
    admin_engine.dispose()


@pytest.fixture(scope="session", autouse=True)
def migrated_database():
    url = make_url(settings.DATABASE_URL)
    # Every test truncates all tables: refuse to run against anything but a test database
    if not url.database.endswith("_test"):
        pytest.exit(f"Refusing to run tests against non-test database '{url.database}'")

    _ensure_test_database_exists(url)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))

    # Build the schema through the real migrations, so migration drift is caught
    command.upgrade(Config("alembic.ini"), "head")
    yield
    engine.dispose()


@pytest.fixture(scope="session")
def redis_sync():
    client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
    yield client
    client.close()


@pytest.fixture(autouse=True)
def clean_state(redis_sync):
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE"))
    redis_sync.flushdb()
    yield


@pytest.fixture(scope="session")
def client():
    # One client for the whole session: the async Redis pool is bound to the client's event loop
    with TestClient(app) as test_client:
        yield test_client
