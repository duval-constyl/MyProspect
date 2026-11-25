import httpx
import pytest
import respx

from app.domain import Circle, OsmBusiness, RegistryCompany
from app.sources import osm
from app.sources.osm import OVERPASS_URL, fetch_osm_businesses, match_osm_to_registry

LYON = Circle(lat=45.764, long=4.8357, radius_km=2)
METERS_PER_DEGREE_LAT = 111_320


@pytest.fixture(autouse=True)
def no_real_sleep(monkeypatch):
    pauses: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        pauses.append(seconds)

    monkeypatch.setattr(osm, "_sleep", fake_sleep)
    monkeypatch.setattr(osm, "_blocked_until", 0.0)
    return pauses


def company(siret: str, name: str, lat: float | None = 45.764, long: float | None = 4.8357):
    return RegistryCompany(
        siret=siret,
        name=name,
        naf="96.02A",
        effectif_code="01",
        created_on=None,
        lat=lat,
        long=long,
        address="1 RUE DE LA REPUBLIQUE 69001 LYON",
        is_individual=False,
        closed=False,
    )


def business(osm_id: str, name: str, lat: float = 45.764, long: float = 4.8357):
    return OsmBusiness(
        osm_id=osm_id, name=name, lat=lat, long=long, phone=None, email=None, website=None
    )


@respx.mock
async def test_parses_phone_email_website_tags():
    route = respx.post(OVERPASS_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "elements": [
                    {
                        "type": "node",
                        "id": 101,
                        "lat": 45.7651,
                        "lon": 4.8362,
                        "tags": {
                            "name": "Salon Éclat",
                            "shop": "hairdresser",
                            "phone": "+33 4 78 00 00 01",
                            "website": "https://salon-eclat.fr",
                        },
                    },
                    {
                        "type": "way",
                        "id": 202,
                        "center": {"lat": 45.7633, "lon": 4.8341},
                        "tags": {
                            "name": "Garage Martin",
                            "shop": "car_repair",
                            "contact:phone": "04 78 00 00 02",
                            "contact:email": "contact@garage-martin.fr",
                        },
                    },
                ]
            },
        )
    )

    businesses = await fetch_osm_businesses(LYON)

    assert businesses == [
        OsmBusiness(
            osm_id="node/101",
            name="Salon Éclat",
            lat=45.7651,
            long=4.8362,
            phone="+33 4 78 00 00 01",
            email=None,
            website="https://salon-eclat.fr",
        ),
        OsmBusiness(
            osm_id="way/202",
            name="Garage Martin",
            lat=45.7633,
            long=4.8341,
            phone="04 78 00 00 02",
            email="contact@garage-martin.fr",
            website=None,
        ),
    ]
    request = route.calls[0].request
    query = httpx.QueryParams(request.content.decode())["data"]
    for key in ("shop", "amenity", "craft", "office"):
        assert f'["{key}"]["name"](around:2000,45.764,4.8357)' in query
    assert request.headers["User-Agent"].startswith("MyProspect/")


def test_match_requires_distance_and_name():
    companies = [
        company("11111111100011", "SALON ECLAT"),
        company("22222222200022", "GARAGE MARTIN SARL"),
    ]
    far_lat = 45.764 + 500 / METERS_PER_DEGREE_LAT
    near_lat = 45.764 + 20 / METERS_PER_DEGREE_LAT
    businesses = [
        business("node/1", "Salon Éclat", lat=far_lat),  # right name, 500 m away
        business("node/2", "Garage Martin", lat=near_lat),  # close name, 20 m away
    ]

    matches = match_osm_to_registry(companies, businesses)

    assert matches == {"22222222200022": businesses[1]}


def test_no_match_returns_empty():
    companies = [company("11111111100011", "BOULANGERIE DUPONT")]
    businesses = [business("node/1", "Pharmacie des Terreaux")]

    assert match_osm_to_registry(companies, businesses) == {}


def test_company_without_position_is_never_matched():
    companies = [company("11111111100011", "SALON ECLAT", lat=None, long=None)]
    businesses = [business("node/1", "Salon Eclat")]

    assert match_osm_to_registry(companies, businesses) == {}


def test_one_osm_business_matches_one_company_only():
    companies = [
        company("11111111100011", "SALON ECLAT"),
        company("22222222200022", "SALON ECLAT PLUS"),
    ]
    businesses = [business("node/1", "Salon Eclat")]

    assert match_osm_to_registry(companies, businesses) == {"11111111100011": businesses[0]}


@respx.mock
async def test_overpass_timeout_returns_empty_list_not_exception():
    respx.post(OVERPASS_URL).mock(side_effect=httpx.ReadTimeout("trop long"))

    assert await fetch_osm_businesses(LYON) == []


@respx.mock
async def test_overpass_runtime_error_remark_returns_empty_list():
    respx.post(OVERPASS_URL).mock(
        return_value=httpx.Response(
            200,
            json={"elements": [], "remark": "runtime error: Query timed out in \"query\""},
        )
    )

    assert await fetch_osm_businesses(LYON) == []


@respx.mock
async def test_waits_30s_after_429_before_next_query(no_real_sleep):
    respx.post(OVERPASS_URL).mock(
        side_effect=[httpx.Response(429), httpx.Response(200, json={"elements": []})]
    )

    assert await fetch_osm_businesses(LYON) == []
    assert no_real_sleep == []
    assert await fetch_osm_businesses(LYON) == []
    assert len(no_real_sleep) == 1
    assert no_real_sleep[0] == pytest.approx(30, abs=1)
