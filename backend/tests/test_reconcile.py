from datetime import UTC, datetime, timedelta

import httpx
import respx
from sqlalchemy import select

from app.collect import create_collection, run_collection
from app.db import get_session_factory
from app.models import Job, Prospect
from app.reconcile import find_duplicates, mark_closed
from app.sources.registry import SEARCH_URL, registry_lookup_by_siret
from tests.test_collect import CIRCLE_ZONE, LAT, LONG, SALON, fake_osm, fake_registry

LYON = (LAT, LONG)
TEN_METRES = 10 / 111_320
STARTED = datetime(2026, 11, 25, 9, 0, tzinfo=UTC)


def finished_collection(session, started_at=STARTED) -> int:
    job = create_collection(session, "circle", CIRCLE_ZONE, ["96.02A"])
    job.state, job.started_at = "done", started_at
    session.commit()
    return job.zone_id


def collected_at(session, prospect_id: int, when: datetime) -> None:
    session.get(Prospect, prospect_id).last_collected_at = when
    session.commit()


def fake_lookup(states: dict[str, str | None]):
    asked = []

    async def lookup(siret: str, client=None):
        asked.append(siret)
        return states.get(siret)

    lookup.asked = asked
    return lookup


def test_duplicates_same_name_within_30m(add, db_session):
    a = add("11111111100011", "SALON ECLAT", LYON)
    b = add("22222222200022", "Salon Éclat SARL", (LAT + TEN_METRES, LONG))
    add("33333333300033", "GARAGE MARTIN", (LAT + TEN_METRES, LONG))

    assert find_duplicates(db_session) == [(a.id, b.id)]


def test_same_name_far_apart_not_duplicate(add, db_session):
    add("11111111100011", "SALON ECLAT", LYON)
    add("22222222200022", "SALON ECLAT", (LAT + 50 * TEN_METRES, LONG))  # 500 m
    add("33333333300033", "SALON ECLAT", None)  # no position: never a duplicate

    assert find_duplicates(db_session) == []


async def test_absent_and_closed_company_is_marked_closed(add, db_session):
    zone_id = finished_collection(db_session)
    absent = add("11111111100011", "SALON FERME", LYON)
    present = add("22222222200022", "SALON OUVERT", LYON)
    collected_at(db_session, absent.id, STARTED - timedelta(days=7))
    collected_at(db_session, present.id, STARTED + timedelta(minutes=1))
    lookup = fake_lookup({absent.siret: "closed", present.siret: "closed"})

    count = await mark_closed(db_session, zone_id, lookup=lookup)

    db_session.expire_all()
    assert count == 1
    assert lookup.asked == [absent.siret]  # present in the last collection: not asked
    assert db_session.get(Prospect, absent.id).closed is True
    assert db_session.get(Prospect, present.id).closed is False


async def test_absent_but_still_active_is_kept(add, db_session):
    zone_id = finished_collection(db_session)
    active = add("11111111100011", "SALON ACTIF", LYON)
    unknown = add("22222222200022", "SALON INCONNU", LYON)
    outside = add("33333333300033", "SALON PARISIEN")  # Paris: outside the Lyon zone
    for prospect in (active, unknown, outside):
        collected_at(db_session, prospect.id, STARTED - timedelta(days=7))
    lookup = fake_lookup({active.siret: "active", unknown.siret: None, outside.siret: "closed"})

    count = await mark_closed(db_session, zone_id, lookup=lookup)

    db_session.expire_all()
    assert count == 0
    assert sorted(lookup.asked) == sorted([active.siret, unknown.siret])
    assert not any(db_session.get(Prospect, p.id).closed for p in (active, unknown, outside))


async def test_other_trades_in_the_zone_are_not_looked_up(add, db_session):
    zone_id = finished_collection(db_session)  # the zone collects hairdressers (96.02A) only
    garage = add("11111111100011", "GARAGE DU COIN", LYON, naf="45.20A")  # collected by another zone
    collected_at(db_session, garage.id, STARTED - timedelta(days=7))
    lookup = fake_lookup({garage.siret: "closed"})

    count = await mark_closed(db_session, zone_id, lookup=lookup)

    db_session.expire_all()
    assert count == 0
    assert lookup.asked == []  # never searched by this zone: its absence means nothing
    assert db_session.get(Prospect, garage.id).closed is False


async def test_zone_without_finished_collection_marks_nothing(db_session):
    job = create_collection(db_session, "circle", CIRCLE_ZONE, ["96.02A"])

    assert await mark_closed(db_session, job.zone_id, lookup=fake_lookup({})) == 0


def test_closed_prospects_hidden_from_default_list_but_kept_in_database(client, add, db_session):
    add("11111111100011", "SALON OUVERT")
    closed = add("22222222200022", "SALON FERME")
    db_session.get(Prospect, closed.id).closed = True
    db_session.commit()

    default = client.get("/prospects").json()
    everything = client.get("/prospects", params={"include_closed": "true"}).json()
    stats = client.get("/prospects/stats", params={"bbox": "2.2,48.8,2.5,48.95"}).json()
    clusters = client.get("/prospects/clusters", params={"bbox": "-5,41,10,52", "zoom": 18}).json()

    assert [p["name"] for p in default["items"]] == ["SALON OUVERT"]
    assert sorted(p["name"] for p in everything["items"]) == ["SALON FERME", "SALON OUVERT"]
    assert stats["in_view"] == 1
    assert len(clusters["clusters"]) == 1
    assert db_session.scalar(select(Prospect.id).where(Prospect.siret == "22222222200022")) == closed.id


def test_duplicates_route_lists_pairs_with_names(client, add):
    a = add("11111111100011", "SALON ECLAT", LYON)
    b = add("22222222200022", "SALON ECLAT", (LAT + TEN_METRES, LONG))

    pairs = client.get("/prospects/duplicates").json()

    assert pairs == [{"first": {"id": a.id, "name": "SALON ECLAT"}, "second": {"id": b.id, "name": "SALON ECLAT"}}]


async def test_collection_records_its_start(db_session):
    job = create_collection(db_session, "circle", CIRCLE_ZONE, ["96.02A"])

    await run_collection(job.id, get_session_factory(), registry=fake_registry(SALON), osm=fake_osm())

    db_session.expire_all()
    assert db_session.get(Job, job.id).started_at is not None


@respx.mock
async def test_registry_lookup_by_siret_reads_the_establishment_state():
    def answer(request):
        siret = request.url.params["q"]
        states = {"11111111100011": "F", "22222222200022": "A"}
        if siret not in states:
            return httpx.Response(200, json={"results": [], "total_results": 0})
        return httpx.Response(
            200,
            json={"results": [{"etat_administratif": "A", "matching_etablissements": [
                {"siret": siret, "etat_administratif": states[siret]}]}]},
        )

    respx.get(SEARCH_URL).mock(side_effect=answer)

    assert await registry_lookup_by_siret("11111111100011") == "closed"
    assert await registry_lookup_by_siret("22222222200022") == "active"
    assert await registry_lookup_by_siret("33333333300033") is None


@respx.mock
async def test_registry_lookup_error_is_unknown(monkeypatch):
    from app.sources import registry

    async def no_sleep(seconds):
        return None

    monkeypatch.setattr(registry, "_sleep", no_sleep)
    respx.get(SEARCH_URL).mock(return_value=httpx.Response(500))

    assert await registry_lookup_by_siret("11111111100011") is None
