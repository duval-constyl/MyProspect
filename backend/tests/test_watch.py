from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.collect import create_collection, run_collection
from app.models import Alert, Exclusion, Job, Prospect, Zone
from app.watch import build_scheduler, run_watch
from app.db import get_session_factory
from tests.test_collect import CIRCLE_ZONE, GARAGE, SALON, fake_analyze, fake_osm, fake_registry
from tests.test_multi_offer import no_tech_offers

T0 = datetime(2026, 11, 2, 8, 0, tzinfo=UTC)


def watched_zone(session, every_days: int = 7, last_watch_at=None) -> int:
    job = create_collection(session, "circle", CIRCLE_ZONE, ["96.02A"])
    job.state = "done"
    zone = session.get(Zone, job.zone_id)
    zone.watch, zone.watch_every_days, zone.last_watch_at = True, every_days, last_watch_at
    session.commit()
    return zone.id


def collector(*companies, fail=False):
    calls = []

    async def collect(job_id, session_factory):
        calls.append(job_id)
        await run_collection(
            job_id, session_factory,
            registry=fake_registry(*companies, fail_at_end=fail),
            osm=fake_osm(), analyze=fake_analyze(), tech_offers=no_tech_offers(),
        )

    collect.calls = calls
    return collect


def lookup_from(states):
    async def lookup(siret, client=None):
        return states.get(siret)

    return lookup


async def watch(now, collect, lookup=None) -> int:
    return await run_watch(get_session_factory(), now, collect=collect, lookup=lookup or lookup_from({}))


def alerts(session) -> list[tuple[str, str]]:
    session.expire_all()
    rows = session.execute(
        select(Alert.kind, Prospect.siret).join(Prospect, Prospect.id == Alert.prospect_id).order_by(Alert.id)
    ).all()
    return [(kind, siret) for kind, siret in rows]


async def test_first_run_sets_the_baseline_without_alert(db_session):
    zone_id = watched_zone(db_session)

    created = await watch(T0, collector(SALON, GARAGE))

    assert created == 0
    assert alerts(db_session) == []
    assert db_session.get(Zone, zone_id).last_watch_at == T0


async def test_new_company_in_watched_zone_creates_one_alert(db_session):
    watched_zone(db_session)
    await watch(T0, collector(SALON))

    created = await watch(T0 + timedelta(days=8), collector(SALON, GARAGE))

    assert created == 1
    assert alerts(db_session) == [("new_company", GARAGE.siret)]


async def test_run_twice_without_change_creates_no_new_alert(db_session):
    watched_zone(db_session)
    await watch(T0, collector(SALON, GARAGE))

    first = await watch(T0 + timedelta(days=8), collector(SALON, GARAGE))
    second = await watch(T0 + timedelta(days=16), collector(SALON, GARAGE))

    assert (first, second) == (0, 0)
    assert alerts(db_session) == []


async def test_zone_not_due_is_skipped(db_session):
    watched_zone(db_session, every_days=7, last_watch_at=T0 - timedelta(days=1))
    collect = collector(SALON)

    created = await watch(T0, collect)

    assert created == 0
    assert collect.calls == []


async def test_unwatched_zone_is_never_collected(db_session):
    job = create_collection(db_session, "circle", CIRCLE_ZONE, ["96.02A"])
    collect = collector(SALON)

    await watch(T0, collect)

    assert collect.calls == []
    assert db_session.get(Zone, job.zone_id).last_watch_at is None


async def test_closed_company_creates_closed_alert(db_session):
    watched_zone(db_session)
    await watch(T0, collector(SALON, GARAGE))

    created = await watch(T0 + timedelta(days=8), collector(GARAGE), lookup_from({SALON.siret: "closed"}))

    assert created == 1
    assert alerts(db_session) == [("closed", SALON.siret)]
    assert db_session.scalar(select(Prospect.closed).where(Prospect.siret == SALON.siret)) is True


async def test_excluded_company_never_alerts(db_session):
    watched_zone(db_session)
    await watch(T0, collector(SALON))
    db_session.add_all([
        Exclusion(siret=GARAGE.siret, reason="do_not_contact"),  # new but excluded: never created
        Exclusion(siret=SALON.siret, reason="do_not_contact"),  # kept, then closed: no alert either
    ])
    db_session.commit()

    created = await watch(T0 + timedelta(days=8), collector(GARAGE), lookup_from({SALON.siret: "closed"}))

    assert created == 0
    assert alerts(db_session) == []


async def test_failed_collection_creates_no_alert_and_does_not_crash_scheduler(db_session):
    zone_id = watched_zone(db_session)
    await watch(T0, collector(SALON))

    failed = await watch(T0 + timedelta(days=8), collector(SALON, GARAGE, fail=True))

    async def crashing(job_id, session_factory):
        raise RuntimeError("bug")

    crashed = await watch(T0 + timedelta(days=9), crashing)

    assert (failed, crashed) == (0, 0)
    assert alerts(db_session) == []
    assert db_session.get(Zone, zone_id).last_watch_at == T0  # retried at the next check
    jobs = db_session.scalars(select(Job.state).where(Job.zone_id == zone_id).order_by(Job.id)).all()
    assert "failed" in jobs


def test_scheduler_checks_every_hour():
    scheduler = build_scheduler()

    job = scheduler.get_job("watch")
    assert job is not None
    assert job.trigger.interval == timedelta(hours=1)
    assert job.max_instances == 1


# --- Routes -------------------------------------------------------------------


def test_patch_zone_watch_settings(client, db_session):
    zone_id = create_collection(db_session, "circle", CIRCLE_ZONE, ["96.02A"]).zone_id

    response = client.patch(f"/zones/{zone_id}", json={"watch": True, "watch_every_days": 14})
    invalid = client.patch(f"/zones/{zone_id}", json={"watch_every_days": 0})

    assert response.status_code == 200
    assert (response.json()["watch"], response.json()["watch_every_days"]) == (True, 14)
    assert invalid.status_code == 422
    assert client.patch("/zones/999999", json={"watch": True}).status_code == 404
    listed = client.get("/zones").json()[0]
    assert (listed["watch"], listed["watch_every_days"], listed["last_watch_at"]) == (True, 14, None)


async def test_alerts_list_and_seen(client, db_session):
    watched_zone(db_session)
    await watch(T0, collector(SALON))
    await watch(T0 + timedelta(days=8), collector(SALON, GARAGE))

    unseen = client.get("/alerts", params={"unseen": "true"}).json()

    assert len(unseen) == 1
    alert = unseen[0]
    assert (alert["kind"], alert["prospect_name"], alert["seen_at"]) == ("new_company", "GARAGE MARTIN", None)
    assert alert["zone_label"] == "Cercle de 1 km"
    seen = client.post(f"/alerts/{alert['id']}/seen")
    assert seen.status_code == 200 and seen.json()["seen_at"]
    assert client.get("/alerts", params={"unseen": "true"}).json() == []
    assert len(client.get("/alerts").json()) == 1
    assert client.post("/alerts/999999/seen").status_code == 404
    assert db_session.scalar(select(func.count()).select_from(Alert)) == 1
