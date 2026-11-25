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

ROOT_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


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


@pytest.fixture
def client(test_database):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client
