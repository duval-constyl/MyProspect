"""Collection orchestrator: zone -> registry -> exclusions -> OSM -> upsert -> sites -> scores.

A collection runs in the background; its progress lives in the `jobs` table.
Results already obtained are kept when a source fails midway.
"""

import asyncio
import dataclasses
import logging
from datetime import date

from geoalchemy2 import WKTElement
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker

from app.analysis.site import analyze_site, new_site_client
from app.config import get_settings
from app.domain import Circle, OsmBusiness, RegistryCompany, SiteAnalysis
from app.geo import point_in_zone, zone_to_circles
from app.http import new_http_client
from app.models import Contact, Exclusion, Job, Prospect, ScoreRow, SiteAnalysisRow, Zone
from app.scoring.web import score_web
from app.sources.osm import fetch_osm_businesses, match_osm_to_registry
from app.sources.pagespeed import mobile_perf
from app.sources.registry import RegistryUnavailable, fetch_near_point

logger = logging.getLogger(__name__)

PARALLEL_SITE_ANALYSES = 5
API_TIMEOUT_S = 60.0
INTERRUPTED = "interrompu"


def create_collection(session: Session, kind: str, geojson: dict, naf_codes: list[str]) -> Job:
    zone = Zone(kind=kind, geojson=geojson, naf_codes=naf_codes)
    session.add(zone)
    session.flush()
    job = Job(zone_id=zone.id, state="pending", done=0, total=0)
    session.add(job)
    session.commit()
    return job


def fail_interrupted_jobs(session: Session) -> int:
    """Jobs left running or pending by a stopped API will never finish: mark them failed."""
    result = session.execute(
        update(Job)
        .where(Job.state.in_(("pending", "running")))
        .values(state="failed", error=INTERRUPTED)
    )
    session.commit()
    return result.rowcount


async def run_collection(
    job_id: int,
    session_factory: sessionmaker[Session],
    registry=fetch_near_point,
    osm=fetch_osm_businesses,
    analyze=analyze_site,
) -> None:
    with session_factory() as session:
        job = session.get(Job, job_id)
        zone = session.get(Zone, job.zone_id)
        job.state, job.error = "running", None
        session.commit()

        api_client = new_http_client(timeout=API_TIMEOUT_S)
        site_client = new_site_client()
        error = None
        try:
            companies, circles, error = await _fetch_companies(registry, zone, api_client)
            companies = _without_exclusions(session, companies)
            job.total = len(companies)
            session.commit()

            places = await _fetch_places(osm, circles, api_client) if companies else []
            matches = match_osm_to_registry(list(companies.values()), places)
            today = date.today()
            prospect_ids = {
                siret: _upsert_prospect(session, company, matches.get(siret), today)
                for siret, company in companies.items()
            }
            session.commit()

            await _analyze_and_score(session, job_id, prospect_ids, analyze, api_client, site_client)
        except Exception as exc:  # noqa: BLE001 - the job must always end with a state
            logger.exception("Récolte %s interrompue", job_id)
            session.rollback()
            error = error or f"Erreur inattendue pendant la récolte ({type(exc).__name__})."
        finally:
            await api_client.aclose()
            await site_client.aclose()

        job = session.get(Job, job_id)
        job.state = "failed" if error else "done"
        job.error = error
        session.execute(update(Zone).where(Zone.id == zone.id).values(collected_at=func.now()))
        session.commit()


async def _fetch_companies(
    registry, zone: Zone, client
) -> tuple[dict[str, RegistryCompany], list[Circle], str | None]:
    """Companies of the zone by SIRET, the circles that produced some, and the error if any."""
    companies: dict[str, RegistryCompany] = {}
    useful_circles: list[Circle] = []
    try:
        for circle in zone_to_circles(zone.kind, zone.geojson):
            async for company in registry(circle, zone.naf_codes, client=client):
                if not _inside(zone, company):
                    continue
                companies.setdefault(company.siret, company)
                if circle not in useful_circles:
                    useful_circles.append(circle)
    except RegistryUnavailable as exc:
        return companies, useful_circles, f"Récolte interrompue : {exc}"
    return companies, useful_circles, None


def _inside(zone: Zone, company: RegistryCompany) -> bool:
    """Circles covering a polygon spill over it: keep what is really inside.

    A company without coordinates cannot be checked; the registry found it in the
    circle, so it is kept.
    """
    if zone.kind == "circle" or company.lat is None or company.long is None:
        return True
    return point_in_zone(zone.kind, zone.geojson, company.lat, company.long)


def _without_exclusions(
    session: Session, companies: dict[str, RegistryCompany]
) -> dict[str, RegistryCompany]:
    if not companies:
        return companies
    excluded = set(
        session.scalars(select(Exclusion.siret).where(Exclusion.siret.in_(list(companies))))
    )
    return {siret: c for siret, c in companies.items() if siret not in excluded}


async def _fetch_places(osm, circles: list[Circle], client) -> list[OsmBusiness]:
    """One Overpass query per useful circle, one after the other (usage policy)."""
    places: dict[str, OsmBusiness] = {}
    for circle in circles:
        for place in await osm(circle, client=client):
            places.setdefault(place.osm_id, place)
    return list(places.values())


def _upsert_prospect(
    session: Session, company: RegistryCompany, place: OsmBusiness | None, today: date
) -> int:
    values = {
        "siret": company.siret,
        "name": company.name,
        "naf": company.naf,
        "effectif_code": company.effectif_code,
        "created_on": company.created_on,
        "geom": _point(company),
        "address": company.address,
        "is_individual": company.is_individual,
        "closed": company.closed,
        "opposed_to_prospecting": company.opposed_to_prospecting,
    }
    statement = insert(Prospect).values(**values)
    statement = statement.on_conflict_do_update(
        index_elements=[Prospect.siret],
        set_={
            **{key: statement.excluded[key] for key in values if key != "siret"},
            "last_collected_at": func.now(),
        },
    ).returning(Prospect.id)
    prospect_id = session.execute(statement).scalar_one()

    if place is not None:
        for kind, value in (("phone", place.phone), ("email", place.email), ("website", place.website)):
            if value:
                _upsert_contact(session, prospect_id, kind, value, "osm", today)
    return prospect_id


def _point(company: RegistryCompany) -> WKTElement | None:
    if company.lat is None or company.long is None:
        return None
    return WKTElement(f"POINT({company.long} {company.lat})", srid=4326)


def _upsert_contact(
    session: Session, prospect_id: int, kind: str, value: str, source: str, seen_on: date
) -> None:
    statement = insert(Contact).values(
        prospect_id=prospect_id, kind=kind, value=value, source=source, seen_on=seen_on
    )
    session.execute(
        statement.on_conflict_do_update(
            index_elements=[Contact.prospect_id, Contact.kind, Contact.value],
            set_={"source": statement.excluded.source, "seen_on": statement.excluded.seen_on},
        )
    )


async def _analyze_and_score(
    session: Session, job_id: int, prospect_ids: dict[str, int], analyze, api_client, site_client
) -> None:
    api_key = get_settings().pagespeed_api_key
    slots = asyncio.Semaphore(PARALLEL_SITE_ANALYSES)

    async def process(prospect_id: int) -> None:
        website = _latest_website(session, prospect_id)
        analysis = None
        if website is not None:
            async with slots:
                analysis = await analyze(website, client=site_client)
                if analysis.reachable and api_key:
                    perf = await mobile_perf(analysis.url, api_key, client=api_client)
                    analysis = dataclasses.replace(analysis, mobile_perf=perf)
        # No await below: this block runs alone even with parallel analyses.
        if analysis is not None:
            _upsert_site_analysis(session, prospect_id, analysis)
        score = score_web(website is not None, analysis)
        _upsert_score(session, prospect_id, score)
        session.execute(update(Job).where(Job.id == job_id).values(done=Job.done + 1))
        session.commit()

    async with asyncio.TaskGroup() as group:
        for prospect_id in prospect_ids.values():
            group.create_task(process(prospect_id))


def _latest_website(session: Session, prospect_id: int) -> str | None:
    return session.scalar(
        select(Contact.value)
        .where(Contact.prospect_id == prospect_id, Contact.kind == "website")
        .order_by(Contact.seen_on.desc(), Contact.id.desc())
        .limit(1)
    )


def _upsert_site_analysis(session: Session, prospect_id: int, analysis: SiteAnalysis) -> None:
    values = dataclasses.asdict(analysis)
    statement = insert(SiteAnalysisRow).values(prospect_id=prospect_id, **values)
    session.execute(
        statement.on_conflict_do_update(
            index_elements=[SiteAnalysisRow.prospect_id],
            set_={key: statement.excluded[key] for key in values},
        )
    )


def _upsert_score(session: Session, prospect_id: int, score) -> None:
    statement = insert(ScoreRow).values(
        prospect_id=prospect_id,
        offer=str(score.offer),
        value=score.value,
        tier=score.tier,
        reasons=[dataclasses.asdict(reason) for reason in score.reasons],
    )
    session.execute(
        statement.on_conflict_do_update(
            index_elements=[ScoreRow.prospect_id, ScoreRow.offer],
            set_={
                "value": statement.excluded.value,
                "tier": statement.excluded.tier,
                "reasons": statement.excluded.reasons,
                "computed_at": func.now(),
            },
        )
    )
