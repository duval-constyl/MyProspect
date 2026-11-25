"""Watched zones: collect them again on a schedule and raise alerts (V3 plan, Task 5).

Each due zone gets a fresh collection. New companies located in the zone and companies
newly found closed give one alert each (never twice: unique per zone, prospect, kind).
The first run of a newly watched zone only records the starting point, without alert.
A failed collection gives no alert and the zone is tried again at the next check.
"""

import logging
from datetime import UTC, datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker

from app.collect import run_collection
from app.db import get_session_factory
from app.geo import point_in_zone
from app.models import Alert, Exclusion, Job, Prospect, Zone
from app.reconcile import mark_closed
from app.sources.registry import registry_lookup_by_siret

logger = logging.getLogger(__name__)

CHECK_EVERY = timedelta(hours=1)


def zone_label(zone: Zone) -> str:
    properties = (zone.geojson or {}).get("properties") or {}
    if zone.kind == "commune":
        name = properties.get("nom") or "Commune"
        departement = properties.get("codeDepartement")
        return f"{name} ({departement})" if departement else name
    if zone.kind == "circle":
        return f"Cercle de {float(properties.get('radius_km', 0)):g} km"
    return "Dessin libre"


def is_due(zone: Zone, now: datetime) -> bool:
    return zone.last_watch_at is None or zone.last_watch_at + timedelta(days=zone.watch_every_days) <= now


async def run_watch(
    session_factory: sessionmaker[Session],
    now: datetime,
    collect=run_collection,
    lookup=registry_lookup_by_siret,
) -> int:
    """Collect every due watched zone; returns how many alerts were created."""
    with session_factory() as session:
        due = [zone.id for zone in session.scalars(select(Zone).where(Zone.watch.is_(True))) if is_due(zone, now)]
    created = 0
    for zone_id in due:
        try:
            created += await _watch_zone(session_factory, zone_id, now, collect, lookup)
        except Exception:  # noqa: BLE001 - one zone must never stop the others or the scheduler
            logger.exception("Veille de la zone %s interrompue", zone_id)
    return created


def _ids_in_zone(session: Session, zone: Zone, *conditions) -> set[int]:
    rows = session.execute(
        select(Prospect.id, func.ST_Y(Prospect.geom), func.ST_X(Prospect.geom)).where(
            Prospect.geom.is_not(None), *conditions
        )
    )
    return {pid for pid, lat, long in rows if point_in_zone(zone.kind, zone.geojson, lat, long)}


async def _watch_zone(session_factory, zone_id: int, now: datetime, collect, lookup) -> int:
    with session_factory() as session:
        zone = session.get(Zone, zone_id)
        baseline = zone.last_watch_at is None
        job = Job(zone_id=zone_id, state="pending", done=0, total=0)
        session.add(job)
        session.commit()
        job_id = job.id

    await collect(job_id, session_factory)

    with session_factory() as session:
        job = session.get(Job, job_id)
        if job.state != "done":
            return 0
        zone = session.get(Zone, zone_id)
        closed_before = _ids_in_zone(session, zone, Prospect.closed.is_(True))
        await mark_closed(session, zone_id, lookup=lookup)
        created = 0
        if not baseline:
            new_ids = _ids_in_zone(
                session, zone, Prospect.closed.is_(False), Prospect.first_seen_at >= job.started_at
            )
            newly_closed = _ids_in_zone(session, zone, Prospect.closed.is_(True)) - closed_before
            excluded = set(
                session.scalars(
                    select(Prospect.id).join(Exclusion, Exclusion.siret == Prospect.siret)
                )
            )
            candidates = [(pid, "new_company") for pid in sorted(new_ids - excluded)]
            candidates += [(pid, "closed") for pid in sorted(newly_closed - excluded)]
            for prospect_id, kind in candidates:
                inserted = session.execute(
                    insert(Alert)
                    .values(zone_id=zone_id, prospect_id=prospect_id, kind=kind)
                    .on_conflict_do_nothing(index_elements=[Alert.zone_id, Alert.prospect_id, Alert.kind])
                    .returning(Alert.id)
                ).first()
                created += inserted is not None
        zone.last_watch_at = now
        session.commit()
        return created


async def _scheduled_watch() -> None:
    try:
        created = await run_watch(get_session_factory(), datetime.now(UTC))
        if created:
            logger.info("Veille : %s nouvelle(s) alerte(s)", created)
    except Exception:  # noqa: BLE001
        logger.exception("Veille des zones en échec")


def build_scheduler() -> AsyncIOScheduler:
    """Hourly check of the watched zones (started with the API when WATCH_ENABLED)."""
    scheduler = AsyncIOScheduler(timezone="Europe/Paris")
    scheduler.add_job(
        _scheduled_watch, "interval", hours=1, id="watch", max_instances=1, coalesce=True
    )
    return scheduler
