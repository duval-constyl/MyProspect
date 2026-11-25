"""Shared test fixtures.

The suite never touches the development database: DATABASE_URL is forced to
TEST_DATABASE_URL (read from the environment or the root .env file) before the
application is imported. The test database is created on first use.
"""

import os
from pathlib import Path

import pytest
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

BACKEND_DIR = Path(__file__).resolve().parents[1]
ROOT_ENV_FILE = BACKEND_DIR.parent / ".env"


class _TestEnv(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT_ENV_FILE, extra="ignore")

    test_database_url: str = (
        "postgresql+psycopg://prospect:prospect@localhost:5433/prospect_test"
    )


TEST_DATABASE_URL = _TestEnv().test_database_url

os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["HOME_LAT"] = "48.8566"
os.environ["HOME_LONG"] = "2.3522"
os.environ["PAGESPEED_API_KEY"] = ""


@pytest.fixture(scope="session")
def test_database() -> str:
    """Create the test database with PostGIS if it does not exist yet."""
    url = make_url(TEST_DATABASE_URL)
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.scalar(
            text("SELECT 1 FROM pg_database WHERE datname = :name"),
            {"name": url.database},
        )
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{url.database}"'))
    admin.dispose()

    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
    engine.dispose()
    return TEST_DATABASE_URL


@pytest.fixture(scope="session")
def migrated_database(test_database) -> str:
    """Bring the test database schema to the latest Alembic revision."""
    from alembic import command
    from alembic.config import Config

    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.attributes["configure_logger"] = False
    command.upgrade(config, "head")
    return test_database


@pytest.fixture
def db_session(migrated_database):
    """A session on the test database; every table is emptied after the test."""
    import app.models  # noqa: F401  (registers every table on Base.metadata)
    from app.db import Base, get_engine, get_session_factory

    session = get_session_factory()()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
        tables = ", ".join(f'"{table.name}"' for table in Base.metadata.sorted_tables)
        with get_engine().begin() as conn:
            conn.execute(text(f"TRUNCATE TABLE {tables} RESTART IDENTITY CASCADE"))


@pytest.fixture
def client(migrated_database):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client
