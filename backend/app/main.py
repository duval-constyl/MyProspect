from typing import Annotated

from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import get_session

app = FastAPI(title="MyProspect")

SessionDep = Annotated[Session, Depends(get_session)]


@app.get("/health")
def health(session: SessionDep) -> dict[str, object]:
    postgis_version = session.execute(text("SELECT postgis_version()")).scalar_one()
    return {"status": "ok", "postgis": bool(postgis_version)}
