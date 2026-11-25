"""End-to-end smoke test: collect a zone through the API, list, open a card, export.

Registry, OpenStreetMap and websites are simulated: nothing goes to the network.
"""

import csv
import io

from app.collect import run_collection
from app.domain import OsmBusiness
from app.routers.zones import get_collector
from tests.test_collect import (
    CIRCLE_ZONE,
    KM_PER_DEG_LAT,
    LAT,
    LONG,
    company,
    fake_analyze,
    fake_osm,
    fake_registry,
)

COMPANIES = [
    company("11111111100011", "SALON ECLAT"),
    company("22222222200022", "GARAGE MARTIN", lat=LAT + 0.4 / KM_PER_DEG_LAT, naf="45.20A"),
    company("33333333300033", "PLOMBERIE DURAND", lat=LAT - 0.3 / KM_PER_DEG_LAT, naf="43.22A"),
]
PLACES = [
    OsmBusiness("node/1", "Salon Éclat", LAT + 0.00005, LONG, "04 78 00 00 01", None, "https://salon-eclat.fr"),
    OsmBusiness("node/2", "Garage Martin", LAT + 0.4 / KM_PER_DEG_LAT, LONG, None, "contact@garage-martin.fr", None),
]


def test_smoke_collect_list_detail_export(client, db_session):
    async def collector(job_id, session_factory):
        await run_collection(
            job_id,
            session_factory,
            registry=fake_registry(*COMPANIES),
            osm=fake_osm(*PLACES),
            analyze=fake_analyze(),
        )

    client.app.dependency_overrides[get_collector] = lambda: collector
    try:
        started = client.post(
            "/zones/collect",
            json={"kind": "circle", "geojson": CIRCLE_ZONE, "naf_codes": ["96.02A", "45.20A", "43.22A"]},
        )
        assert started.status_code == 202
        job = client.get(f"/jobs/{started.json()['job_id']}").json()
        assert job == {"state": "done", "done": 3, "total": 3, "error": None}

        listing = client.get("/prospects").json()
        assert listing["total"] == 3
        by_name = {item["name"]: item for item in listing["items"]}
        assert by_name["SALON ECLAT"]["score_web"] == 20  # site without HTTPS
        assert by_name["PLOMBERIE DURAND"]["score_web"] == 75  # no site
        assert by_name["PLOMBERIE DURAND"]["phone"] is None

        detail = client.get(f"/prospects/{by_name['SALON ECLAT']['id']}").json()
        assert {(c["kind"], c["source"]) for c in detail["contacts"]} == {("phone", "osm"), ("website", "osm")}
        assert detail["site_analysis"]["https"] is False
        assert detail["scores"][0]["reasons"][0]["code"] == "no_https"
        assert detail["priority"]["reasons"]

        assert len(client.get("/prospects/clusters", params={"bbox": "4.7,45.7,4.9,45.8", "zoom": 18}).json()["clusters"]) == 3
        assert client.get("/prospects/stats", params={"bbox": "4.7,45.7,4.9,45.8"}).json() == {
            "in_view": 3,
            "with_site": 1,
            "without_site": 2,
        }

        exported = client.get("/exports/prospects.csv")
        rows = list(csv.reader(io.StringIO(exported.content.decode("utf-8-sig"))))
        assert rows[0][0] == "siret"
        assert len(rows) - 1 == 3
        assert {row[0] for row in rows[1:]} == {c.siret for c in COMPANIES}
    finally:
        client.app.dependency_overrides.clear()
