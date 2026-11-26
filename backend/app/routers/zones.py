"""Zone collection routes: start a collection, follow its job, list collected zones."""

import re
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Annotated, Literal

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.collect import create_collection, run_collection
from app.db import get_session, get_session_factory
from app.geo import CommuneNotFound, commune_zone, zone_to_circles
from app.models import Job, Zone

router = APIRouter()

SessionDep = Annotated[Session, Depends(get_session)]
Collector = Callable[[int, sessionmaker[Session]], Awaitable[None]]
NAF_CODE = re.compile(r"\d{2}\.\d{2}[A-Z]")


def get_collector() -> Collector:
    """The background collection; replaced in tests so that nothing hits the network."""
    return run_collection


class CollectRequest(BaseModel):
    kind: Literal["commune", "circle", "polygon"]
    # circle: Feature(Point, properties.radius_km); polygon: Polygon/MultiPolygon;
    # commune: its contour, or {"commune": "<nom ou code INSEE>"} to resolve here.
    geojson: dict
    naf_codes: list[str]


class JobOut(BaseModel):
    state: str
    done: int
    total: int
    error: str | None


class ZoneOut(BaseModel):
    id: int
    kind: str
    label: str
    geojson: dict
    naf_codes: list[str]
    collected_at: datetime
    watch: bool
    watch_every_days: int
    last_watch_at: datetime | None


class ZonePatch(BaseModel):
    watch: bool | None = None
    watch_every_days: int | None = Field(default=None, ge=1, le=90)


def _zone_out(zone: Zone) -> ZoneOut:
    from app.watch import zone_label

    return ZoneOut(
        id=zone.id,
        kind=zone.kind,
        label=zone_label(zone),
        geojson=zone.geojson,
        naf_codes=zone.naf_codes,
        collected_at=zone.collected_at,
        watch=zone.watch,
        watch_every_days=zone.watch_every_days,
        last_watch_at=zone.last_watch_at,
    )


@router.post("/zones/collect", status_code=202)
async def collect_zone(
    body: CollectRequest,
    background_tasks: BackgroundTasks,
    session: SessionDep,
    collector: Annotated[Collector, Depends(get_collector)],
) -> dict[str, int]:
    if not body.naf_codes:
        raise HTTPException(422, "Choisissez au moins un métier.")
    invalid = [code for code in body.naf_codes if not NAF_CODE.fullmatch(code)]
    if invalid:
        raise HTTPException(422, f"Code d'activité invalide : {', '.join(invalid)}.")

    geojson = body.geojson
    if body.kind == "commune" and "commune" in geojson:
        try:
            geojson = await commune_zone(str(geojson["commune"]))
        except CommuneNotFound as exc:
            raise HTTPException(422, str(exc)) from None
        except httpx.HTTPError:
            raise HTTPException(502, "Service des communes indisponible, réessayez plus tard.") from None

    try:
        zone_to_circles(body.kind, geojson)  # validates the zone, ZoneTooLarge included
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None

    job = create_collection(session, body.kind, geojson, body.naf_codes)
    background_tasks.add_task(collector, job.id, get_session_factory())
    return {"job_id": job.id}


@router.get("/jobs/{job_id}")
def get_job(job_id: int, session: SessionDep) -> JobOut:
    job = session.get(Job, job_id)
    if job is None:
        raise HTTPException(404, "Récolte introuvable.")
    return JobOut(state=job.state, done=job.done, total=job.total, error=job.error)


@router.get("/zones")
def list_zones(session: SessionDep) -> list[ZoneOut]:
    zones = session.scalars(select(Zone).order_by(Zone.collected_at.desc(), Zone.id.desc()))
    return [_zone_out(zone) for zone in zones]


@router.patch("/zones/{zone_id}")
def update_zone(zone_id: int, body: ZonePatch, session: SessionDep) -> ZoneOut:
    """Watch a zone (collected again every `watch_every_days` days) or stop watching it."""
    zone = session.get(Zone, zone_id)
    if zone is None:
        raise HTTPException(404, "Zone introuvable.")
    for key, value in body.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(zone, key, value)
    session.commit()
    session.refresh(zone)
    return _zone_out(zone)
