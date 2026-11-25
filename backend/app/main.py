import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.collect import fail_interrupted_jobs
from app.db import get_session, get_session_factory
from app.routers import zones

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    try:
        with get_session_factory()() as session:
            fail_interrupted_jobs(session)
    except SQLAlchemyError:
        logger.warning("Base indisponible au démarrage : récoltes interrompues non mises à jour.")
    yield


app = FastAPI(title="MyProspect", lifespan=lifespan)
app.include_router(zones.router)

SessionDep = Annotated[Session, Depends(get_session)]


@app.get("/health")
def health(session: SessionDep) -> dict[str, object]:
    postgis_version = session.execute(text("SELECT postgis_version()")).scalar_one()
    return {"status": "ok", "postgis": bool(postgis_version)}
