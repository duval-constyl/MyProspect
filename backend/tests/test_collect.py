from datetime import UTC, date, datetime

import httpx
import pytest
import respx
from sqlalchemy import func, select

from app.collect import create_collection, run_collection
from app.db import get_session_factory
from app.domain import OsmBusiness, RegistryCompany, SiteAnalysis
from app.geo import GEO_API_URL
from app.models import Contact, Exclusion, Job, Prospect, ScoreRow, SiteAnalysisRow, Tracking, Zone
from app.routers.zones import get_collector
from app.sources.registry import RegistryUnavailable

LAT, LONG = 45.764, 4.8357
KM_PER_DEG_LAT = 110.574
KM_PER_DEG_LONG = 111.320 * 0.6976
CIRCLE_ZONE = {
    "type": "Feature",
    "geometry": {"type": "Point", "coordinates": [LONG, LAT]},
    "properties": {"radius_km": 1},
}


def company(siret: str, name: str, lat: float | None = LAT, long: float | None = LONG, **kw):
    fields = {
        "siret": siret,
        "name": name,
        "naf": "96.02A",
        "effectif_code": "01",
        "created_on": date(2015, 3, 1),
        "lat": lat,
        "long": long,
        "address": "1 RUE DE LA REPUBLIQUE 69001 LYON",
        "is_individual": False,
        "closed": False,
    }
    fields.update(kw)
    return RegistryCompany(**fields)


SALON = company("11111111100011", "SALON ECLAT")
GARAGE = company("22222222200022", "GARAGE MARTIN", lat=LAT + 0.5 / KM_PER_DEG_LAT)
SALON_PLACE = OsmBusiness(
    osm_id="node/1",
    name="Salon Éclat",
    lat=LAT + 0.00005,
    long=LONG,
    phone="+33 4 78 00 00 01",
    email=None,
    website="https://salon-eclat.fr",
)


def fake_registry(*companies: RegistryCompany, fail_at_end: bool = False):
    calls = []

    async def registry(circle, naf_codes, client=None):
        calls.append((circle, naf_codes))
        for item in companies:
            yield item
        if fail_at_end:
            raise RegistryUnavailable("Registre des entreprises indisponible (HTTP 500) pour la page 2.")

    registry.calls = calls
    return registry


def fake_osm(*places: OsmBusiness):
    async def osm(circle, client=None):
        return list(places)

    return osm


def fake_analyze(on_call=None):
    urls = []

    async def analyze(url, client=None):
        urls.append(url)
        if on_call:
            on_call()
        return SiteAnalysis(
            url=url,
            reachable=True,
            https=False,
            has_title=True,
            has_description=True,
            has_h1=True,
            has_viewport=True,
            response_ms=120,
            tech=["wordpress"],
            mobile_perf=None,
            analyzed_at=datetime(2026, 11, 25, tzinfo=UTC),
        )

    analyze.urls = urls
    return analyze


def start_job(session, kind="circle", geojson=CIRCLE_ZONE, naf_codes=("96.02A",)) -> int:
    return create_collection(session, kind, geojson, list(naf_codes)).id


async def collect(job_id, registry, osm=None, analyze=None):
    await run_collection(
        job_id,
        get_session_factory(),
        registry=registry,
        osm=osm or fake_osm(),
        analyze=analyze or fake_analyze(),
    )


def prospect(session, siret) -> Prospect | None:
    return session.scalar(select(Prospect).where(Prospect.siret == siret))


def score_of(session, prospect_id) -> ScoreRow:
    return session.scalar(select(ScoreRow).where(ScoreRow.prospect_id == prospect_id))


async def test_collect_creates_prospects_contacts_scores(db_session):
    job_id = start_job(db_session)
    analyze = fake_analyze()

    await collect(job_id, fake_registry(SALON, GARAGE), fake_osm(SALON_PLACE), analyze)

    db_session.expire_all()
    salon, garage = prospect(db_session, SALON.siret), prospect(db_session, GARAGE.siret)
    assert salon is not None and garage is not None
    contacts = {
        (c.kind, c.value, c.source, c.seen_on)
        for c in db_session.scalars(select(Contact).where(Contact.prospect_id == salon.id))
    }
    assert contacts == {
        ("phone", "+33 4 78 00 00 01", "osm", date.today()),
        ("website", "https://salon-eclat.fr", "osm", date.today()),
    }
    assert analyze.urls == ["https://salon-eclat.fr"]
    analysis = db_session.scalar(select(SiteAnalysisRow).where(SiteAnalysisRow.prospect_id == salon.id))
    assert analysis.reachable is True and analysis.https is False and analysis.tech == ["wordpress"]
    salon_score = score_of(db_session, salon.id)
    assert (salon_score.offer, salon_score.value) == ("web", 20)
    assert salon_score.reasons == [
        {"code": "no_https", "label": "Site sans HTTPS (connexion non sécurisée)", "points": 20}
    ]
    garage_score = score_of(db_session, garage.id)
    assert garage_score.value == 75
    assert [r["code"] for r in garage_score.reasons] == ["no_site"]
    job = db_session.get(Job, job_id)
    assert (job.state, job.done, job.total, job.error) == ("done", 2, 2, None)


async def test_recollect_same_zone_creates_no_duplicates(db_session):
    for _ in range(2):
        await collect(start_job(db_session), fake_registry(SALON, GARAGE), fake_osm(SALON_PLACE))

    db_session.expire_all()
    assert db_session.scalar(select(func.count()).select_from(Prospect)) == 2
    assert db_session.scalar(select(func.count()).select_from(Contact)) == 2
    assert db_session.scalar(select(func.count()).select_from(ScoreRow)) == 2
    assert db_session.scalar(select(func.count()).select_from(SiteAnalysisRow)) == 1


async def test_recollect_keeps_notes_favorite_status(db_session):
    await collect(start_job(db_session), fake_registry(SALON), fake_osm(SALON_PLACE))
    salon = prospect(db_session, SALON.siret)
    db_session.add(
        Tracking(prospect_id=salon.id, status="contacted", favorite=True, notes="Rappeler lundi")
    )
    db_session.commit()
    before = db_session.scalar(select(Tracking).where(Tracking.prospect_id == salon.id))
    snapshot = (before.status, before.favorite, before.notes, before.updated_at)

    await collect(start_job(db_session), fake_registry(SALON), fake_osm(SALON_PLACE))

    db_session.expire_all()
    after = db_session.scalar(select(Tracking).where(Tracking.prospect_id == salon.id))
    assert (after.status, after.favorite, after.notes, after.updated_at) == snapshot


async def test_excluded_siret_is_never_created(db_session):
    db_session.add(Exclusion(siret=SALON.siret, reason="do_not_contact"))
    db_session.commit()
    job_id = start_job(db_session)

    await collect(job_id, fake_registry(SALON, GARAGE), fake_osm(SALON_PLACE))

    db_session.expire_all()
    assert prospect(db_session, SALON.siret) is None
    assert prospect(db_session, GARAGE.siret) is not None
    assert db_session.get(Job, job_id).total == 1


async def test_registry_failure_midway_keeps_prior_results_and_marks_job_failed_with_message(
    db_session,
):
    job_id = start_job(db_session)

    await collect(job_id, fake_registry(SALON, fail_at_end=True), fake_osm(SALON_PLACE))

    db_session.expire_all()
    salon = prospect(db_session, SALON.siret)
    assert salon is not None
    assert score_of(db_session, salon.id).value == 20
    job = db_session.get(Job, job_id)
    assert job.state == "failed"
    assert "Registre des entreprises indisponible" in job.error
    assert (job.done, job.total) == (1, 1)


async def test_progress_counts_done_and_total(db_session):
    job_id = start_job(db_session)
    seen = []

    def record_progress():
        with get_session_factory()() as other:
            job = other.get(Job, job_id)
            seen.append((job.state, job.total))

    places = [
        SALON_PLACE,
        OsmBusiness("node/2", "Garage Martin", GARAGE.lat, GARAGE.long, None, None, "garage-martin.fr"),
    ]
    third = company("33333333300033", "PLOMBERIE DURAND", lat=LAT - 0.3 / KM_PER_DEG_LAT)

    await collect(
        job_id, fake_registry(SALON, GARAGE, third), fake_osm(*places), fake_analyze(record_progress)
    )

    assert seen and all(state_total == ("running", 3) for state_total in seen)
    db_session.expire_all()
    job = db_session.get(Job, job_id)
    assert (job.state, job.done, job.total) == ("done", 3, 3)


async def test_company_without_coordinates_is_stored_but_not_mapped(db_session):
    job_id = start_job(db_session)
    nowhere = company("44444444400044", "SANS POSITION", lat=None, long=None)

    await collect(job_id, fake_registry(nowhere), fake_osm(SALON_PLACE))

    db_session.expire_all()
    stored = prospect(db_session, nowhere.siret)
    assert stored is not None
    assert stored.geom is None
    assert score_of(db_session, stored.id).value == 75
    assert db_session.get(Job, job_id).state == "done"


async def test_opposed_company_is_stored_with_mark(db_session):
    opposed = company("55555555500055", "SALON OPPOSE", opposed_to_prospecting=True)

    await collect(start_job(db_session), fake_registry(opposed, GARAGE))

    db_session.expire_all()
    assert prospect(db_session, opposed.siret).opposed_to_prospecting is True
    assert prospect(db_session, GARAGE.siret).opposed_to_prospecting is False


async def test_polygon_zone_keeps_only_companies_inside(db_session):
    side_lat, side_long = 1 / KM_PER_DEG_LAT, 1 / KM_PER_DEG_LONG
    polygon = {
        "type": "Polygon",
        "coordinates": [[
            [LONG, LAT], [LONG + side_long, LAT], [LONG + side_long, LAT + side_lat],
            [LONG, LAT + side_lat], [LONG, LAT],
        ]],
    }
    inside = company("66666666600066", "DEDANS", lat=LAT + side_lat / 2, long=LONG + side_long / 2)
    outside = company("77777777700077", "DEHORS", lat=LAT - side_lat, long=LONG)

    await collect(start_job(db_session, "polygon", polygon), fake_registry(inside, outside))

    db_session.expire_all()
    assert prospect(db_session, inside.siret) is not None
    assert prospect(db_session, outside.siret) is None


# --- Routes -----------------------------------------------------------------


@pytest.fixture
def collector_calls(client):
    calls = []

    async def recorder(job_id, session_factory):
        calls.append(job_id)

    client.app.dependency_overrides[get_collector] = lambda: recorder
    yield calls
    client.app.dependency_overrides.clear()


def square(side_km: float) -> dict:
    dlat, dlong = side_km / KM_PER_DEG_LAT, side_km / KM_PER_DEG_LONG
    ring = [[LONG, LAT], [LONG + dlong, LAT], [LONG + dlong, LAT + dlat], [LONG, LAT + dlat], [LONG, LAT]]
    return {"type": "Polygon", "coordinates": [ring]}


def test_zone_too_large_returns_422_before_any_call(client, db_session, collector_calls):
    response = client.post(
        "/zones/collect", json={"kind": "polygon", "geojson": square(55), "naf_codes": ["96.02A"]}
    )

    assert response.status_code == 422
    assert "50 km" in response.json()["detail"]
    assert collector_calls == []
    assert db_session.scalar(select(func.count()).select_from(Zone)) == 0


def test_collect_requires_at_least_one_naf_code(client, db_session, collector_calls):
    response = client.post(
        "/zones/collect", json={"kind": "circle", "geojson": CIRCLE_ZONE, "naf_codes": []}
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Choisissez au moins un métier."
    assert collector_calls == []


def test_post_collect_returns_job_and_starts_collection(client, db_session, collector_calls):
    response = client.post(
        "/zones/collect",
        json={"kind": "circle", "geojson": CIRCLE_ZONE, "naf_codes": ["96.02A", "45.20A"]},
    )

    assert response.status_code == 202
    job_id = response.json()["job_id"]
    assert collector_calls == [job_id]
    job = client.get(f"/jobs/{job_id}")
    assert job.status_code == 200
    assert job.json() == {"state": "pending", "done": 0, "total": 0, "error": None}


@respx.mock
def test_commune_name_is_resolved_to_its_contour(client, db_session, collector_calls):
    contour = {"type": "Polygon", "coordinates": [[[4.85, 45.76], [4.88, 45.76], [4.88, 45.78], [4.85, 45.78], [4.85, 45.76]]]}
    respx.get(GEO_API_URL).mock(
        return_value=httpx.Response(
            200,
            json={"type": "FeatureCollection", "features": [{
                "type": "Feature",
                "geometry": contour,
                "properties": {"nom": "Villeurbanne", "code": "69266", "codeDepartement": "69",
                               "population": 156928, "_score": 1},
            }]},
        )
    )

    response = client.post(
        "/zones/collect",
        json={"kind": "commune", "geojson": {"commune": "Villeurbanne"}, "naf_codes": ["96.02A"]},
    )

    assert response.status_code == 202
    zones = client.get("/zones").json()
    assert zones[0]["kind"] == "commune"
    assert zones[0]["geojson"]["geometry"] == contour
    assert zones[0]["geojson"]["properties"]["nom"] == "Villeurbanne"


def test_get_unknown_job_returns_404(client, db_session):
    response = client.get("/jobs/999999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Récolte introuvable."


def test_list_zones_returns_collected_zones_with_date(client, db_session):
    start_job(db_session, naf_codes=("45.20A",))

    zones = client.get("/zones").json()

    assert len(zones) == 1
    assert zones[0]["kind"] == "circle"
    assert zones[0]["naf_codes"] == ["45.20A"]
    assert zones[0]["collected_at"]


def test_interrupted_jobs_are_marked_failed_on_startup(db_session):
    from fastapi.testclient import TestClient

    from app.main import app

    job_id = start_job(db_session)
    job = db_session.get(Job, job_id)
    job.state = "running"
    db_session.commit()

    with TestClient(app):
        pass

    db_session.expire_all()
    job = db_session.get(Job, job_id)
    assert (job.state, job.error) == ("failed", "interrompu")
