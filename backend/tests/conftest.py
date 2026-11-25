"""Shared test fixtures.

The suite never touches the development database: DATABASE_URL is forced to
TEST_DATABASE_URL (read from the environment or the root .env file) before the
application is imported. The test database is created on first use.
"""

import os
from datetime import date
from pathlib import Path

import pytest
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

BACKEND_DIR = Path(__file__).resolve().parents[1]
ROOT_ENV_FILE = BACKEND_DIR.parent / ".env"
PARIS = (48.8566, 2.3522)  # HOME_LAT / HOME_LONG of the test settings
CONTACT_SEEN_ON = date(2026, 11, 20)


class _TestEnv(BaseSettings):
    """Test database settings, read from the environment or the root .env (no default password)."""

    model_config = SettingsConfigDict(env_file=ROOT_ENV_FILE, extra="ignore")

    test_database_url: str | None = None
    postgres_user: str = "prospect"
    postgres_password: str | None = None
    db_port: int = 5433

    def url(self) -> str:
        if self.test_database_url:
            return self.test_database_url
        if not self.postgres_password:
            pytest.exit("TEST_DATABASE_URL ou POSTGRES_PASSWORD manquant : copiez .env.example vers .env.")
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@127.0.0.1:{self.db_port}/prospect_test"
        )


TEST_DATABASE_URL = _TestEnv().url()

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


@pytest.fixture
def add(db_session):
    def add_prospect(
        siret: str,
        name: str,
        position: tuple[float, float] | None = PARIS,
        *,
        score: int | None = None,
        phone: str | None = None,
        email: str | None = None,
        website: str | None = None,
        status: str | None = None,
        favorite: bool | None = None,
        naf: str = "96.02A",
        effectif_code: str | None = "11",
        opposed: bool = False,
        address: str = "12 RUE DE RIVOLI 75004 PARIS 04",
    ):
        from geoalchemy2 import WKTElement

        from app.models import Contact, Prospect, ScoreRow, Tracking

        prospect = Prospect(
            siret=siret,
            name=name,
            naf=naf,
            effectif_code=effectif_code,
            created_on=None,
            geom=WKTElement(f"POINT({position[1]} {position[0]})", srid=4326) if position else None,
            address=address,
            is_individual=False,
            closed=False,
            opposed_to_prospecting=opposed,
        )
        db_session.add(prospect)
        db_session.flush()
        for kind, value in (("phone", phone), ("email", email), ("website", website)):
            if value:
                db_session.add(
                    Contact(prospect_id=prospect.id, kind=kind, value=value, source="osm", seen_on=CONTACT_SEEN_ON)
                )
        if score is not None:
            reasons = [{"code": "no_site", "label": "Aucun site web connu", "points": score}]
            db_session.add(
                ScoreRow(prospect_id=prospect.id, offer="web", value=score, tier=min(6, score // 17 + 1), reasons=reasons)
            )
        if status is not None or favorite is not None:
            db_session.add(
                Tracking(prospect_id=prospect.id, status=status or "new", favorite=bool(favorite), notes="")
            )
        db_session.commit()
        return prospect

    return add_prospect
