from dataclasses import replace

from sqlalchemy import func, select

from app.collect import create_collection, run_collection
from app.db import get_session_factory
from app.domain import JobOffer
from app.models import ScoreRow
from tests.test_collect import (
    CIRCLE_ZONE,
    GARAGE,
    SALON,
    SALON_PLACE,
    fake_analyze,
    fake_osm,
    fake_registry,
    prospect,
)


def no_tech_offers():
    async def tech_offers(departements, client_id, client_secret, client=None):
        return []

    return tech_offers


async def collect(session, registry, osm=None, analyze=None, tech_offers=None):
    job = create_collection(session, "circle", CIRCLE_ZONE, ["96.02A"])
    await run_collection(
        job.id,
        get_session_factory(),
        registry=registry,
        osm=osm or fake_osm(),
        analyze=analyze or fake_analyze(),
        tech_offers=tech_offers or no_tech_offers(),
    )


def scores_of(session, prospect_id) -> dict[str, int]:
    rows = session.scalars(select(ScoreRow).where(ScoreRow.prospect_id == prospect_id))
    return {row.offer: row.value for row in rows}


async def test_collect_stores_three_scores_per_prospect(db_session):
    await collect(db_session, fake_registry(SALON, GARAGE), fake_osm(SALON_PLACE))

    db_session.expire_all()
    salon, garage = prospect(db_session, SALON.siret), prospect(db_session, GARAGE.siret)
    # Salon: site without HTTPS, no booking link; hairdresser takes bookings.
    assert scores_of(db_session, salon.id) == {"web": 20, "mobile": 50, "cloud": 0}
    # Garage: no site at all.
    assert scores_of(db_session, garage.id) == {"web": 75, "mobile": 70, "cloud": 0}


async def test_hiring_offer_adds_cloud_points(db_session):
    seen = {}

    async def tech_offers(departements, client_id, client_secret, client=None):
        seen["departements"] = sorted(departements)
        return [
            JobOffer("O1", "Développeur web", "GARAGE MARTIN", "M1805", "69001", None),
        ]

    await collect(db_session, fake_registry(SALON, GARAGE), tech_offers=tech_offers)

    db_session.expire_all()
    garage = prospect(db_session, GARAGE.siret)
    assert scores_of(db_session, garage.id)["cloud"] == 25
    assert scores_of(db_session, prospect(db_session, SALON.siret).id)["cloud"] == 0
    assert seen["departements"] == ["69"]
    reasons = db_session.scalar(
        select(ScoreRow.reasons).where(ScoreRow.prospect_id == garage.id, ScoreRow.offer == "cloud")
    )
    assert [r["code"] for r in reasons] == ["hiring_tech"]


async def test_recollect_updates_scores_without_duplicates(db_session):
    await collect(db_session, fake_registry(SALON), fake_osm(SALON_PLACE))

    secure = fake_analyze()

    async def analyze_with_https(url, client=None):
        return replace(await secure(url), https=True, has_booking=True)

    await collect(db_session, fake_registry(SALON), fake_osm(SALON_PLACE), analyze_with_https)

    db_session.expire_all()
    salon = prospect(db_session, SALON.siret)
    assert db_session.scalar(select(func.count()).select_from(ScoreRow)) == 3
    assert scores_of(db_session, salon.id) == {"web": 0, "mobile": 0, "cloud": 0}


def add_score(session, prospect_id: int, offer: str, value: int) -> None:
    session.add(
        ScoreRow(
            prospect_id=prospect_id, offer=offer, value=value, tier=min(6, value // 17 + 1),
            reasons=[{"code": f"{offer}_reason", "label": f"Raison {offer}", "points": value}],
        )
    )
    session.commit()


def test_list_sorted_by_mobile_priority_when_offer_is_mobile(client, add, db_session):
    a = add("11111111100011", "SALON A", score=75)
    b = add("22222222200022", "SALON B", score=20)
    add_score(db_session, a.id, "mobile", 0)
    add_score(db_session, b.id, "mobile", 70)

    by_mobile = client.get("/prospects", params={"offer": "mobile"}).json()["items"]
    by_web = client.get("/prospects", params={"offer": "web"}).json()["items"]

    assert [i["name"] for i in by_mobile] == ["SALON B", "SALON A"]
    assert [(i["score"], i["score_web"]) for i in by_mobile] == [(70, 20), (0, 75)]
    assert [i["name"] for i in by_web] == ["SALON A", "SALON B"]
    assert by_web[0]["score"] == 75
    filtered = client.get("/prospects", params={"offer": "mobile", "score_min": 50}).json()
    assert [i["name"] for i in filtered["items"]] == ["SALON B"]


def test_clusters_use_the_selected_offer(client, add, db_session):
    a = add("11111111100011", "SALON A", score=75)
    add_score(db_session, a.id, "mobile", 10)

    web = client.get("/prospects/clusters", params={"bbox": "-5,41,10,52", "zoom": 18}).json()["clusters"]
    mobile = client.get(
        "/prospects/clusters", params={"bbox": "-5,41,10,52", "zoom": 18, "offer": "mobile"}
    ).json()["clusters"]

    assert (web[0]["max_score"], mobile[0]["max_score"]) == (75, 10)


def test_detail_gives_priority_for_each_offer(client, add, db_session):
    a = add("11111111100011", "SALON A", score=60, effectif_code="11")
    add_score(db_session, a.id, "mobile", 70)
    add_score(db_session, a.id, "cloud", 20)

    detail = client.get(f"/prospects/{a.id}").json()

    assert [s["offer"] for s in detail["scores"]] == ["web", "mobile", "cloud"]
    by_offer = detail["priority_by_offer"]
    assert set(by_offer) == {"web", "mobile", "cloud"}
    assert by_offer["web"]["value"] == 30 + 6  # half of 60 + nearby (Paris)
    assert by_offer["mobile"]["value"] == 35 + 6
    assert by_offer["cloud"]["value"] == 10 + 6
    assert detail["priority"] == by_offer["web"]


def test_csv_score_web_column_stays_the_web_score(client, add, db_session):
    a = add("11111111100011", "SALON A", score=75)
    add_score(db_session, a.id, "mobile", 10)

    response = client.get("/exports/prospects.csv", params={"offer": "mobile"})

    lines = response.content.decode("utf-8-sig").splitlines()
    header, row = lines[0].split(","), lines[1].split(",")
    assert dict(zip(header, row))["score_web"] == "75"
