import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.collect import fail_interrupted_jobs
from app.config import get_settings
from app.db import get_session, get_session_factory
from app.routers import alerts, exports, followups, outreach, prospects, tracking, zones
from app.watch import build_scheduler

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    try:
        with get_session_factory()() as session:
            fail_interrupted_jobs(session)
    except SQLAlchemyError:
        logger.warning("Base indisponible au démarrage : récoltes interrompues non mises à jour.")
    scheduler = build_scheduler() if get_settings().watch_enabled else None
    if scheduler is not None:
        scheduler.start()
    try:
        yield
    finally:
        if scheduler is not None:
            scheduler.shutdown(wait=False)


app = FastAPI(title="MyProspect", lifespan=lifespan)
app.include_router(zones.router)
app.include_router(prospects.router)
app.include_router(tracking.router)
app.include_router(exports.router)
app.include_router(outreach.router)
app.include_router(followups.router)
app.include_router(alerts.router)


@app.exception_handler(RequestValidationError)
async def french_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    """Validation errors in French, naming the faulty fields."""
    fields = sorted({str(error["loc"][-1]) for error in exc.errors() if error.get("loc")})
    detail = f"Valeur invalide pour : {', '.join(fields)}." if fields else "Requête invalide."
    return JSONResponse(status_code=422, content={"detail": detail})

SessionDep = Annotated[Session, Depends(get_session)]


@app.get("/health")
def health(session: SessionDep) -> dict[str, object]:
    postgis_version = session.execute(text("SELECT postgis_version()")).scalar_one()
    return {"status": "ok", "postgis": bool(postgis_version)}
