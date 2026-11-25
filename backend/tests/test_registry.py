from datetime import date

import httpx
import pytest
import respx

from app.domain import Circle
from app.sources import registry
from app.sources.registry import (
    REGISTRY_URL,
    RateLimiter,
    RegistryUnavailable,
    fetch_near_point,
)

LYON = Circle(lat=45.764, long=4.8357, radius_km=2)
NAF = ["96.02A", "45.20A"]


def establishment(siret: str, **overrides) -> dict:
    data = {
        "siret": siret,
        "adresse": "12 RUE DE LA REPUBLIQUE 69001 LYON",
        "latitude": "45.7655",
        "longitude": "4.8360",
        "etat_administratif": "A",
        "statut_diffusion_etablissement": "O",
        "activite_principale": "96.02A",
        "liste_enseignes": ["SALON ECLAT"],
        "nom_commercial": None,
        "tranche_effectif_salarie": "NN",
        "date_creation": "2019-10-02",
    }
    data.update(overrides)
    return data


def legal_unit(siren: str, establishments: list[dict], **overrides) -> dict:
    data = {
        "siren": siren,
        "nom_complet": "ECLAT COIFFURE SARL",
        "nature_juridique": "5499",
        "etat_administratif": "A",
        "statut_diffusion": "O",
        "opposition_diffusion_commerciale": False,
        "tranche_effectif_salarie": "01",
        "date_creation": "2015-03-01",
        "activite_principale": "96.02A",
        "complements": {"est_entrepreneur_individuel": False},
        "matching_etablissements": establishments,
    }
    data.update(overrides)
    return data


def page(results: list[dict], number: int) -> httpx.Response:
    return httpx.Response(
        200, json={"results": results, "page": number, "per_page": 25, "total_results": 3}
    )


@pytest.fixture(autouse=True)
def no_real_sleep(monkeypatch):
    """Record the pauses instead of waiting."""
    pauses: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        pauses.append(seconds)

    monkeypatch.setattr(registry, "_sleep", fake_sleep)
    return pauses


async def collect(**kwargs) -> list:
    return [company async for company in fetch_near_point(LYON, NAF, **kwargs)]


@respx.mock
async def test_paginates_until_empty():
    pages = {
        "1": page([legal_unit("111111111", [establishment("11111111100011")]),
                   legal_unit("222222222", [establishment("22222222200022")])], 1),
        "2": page([legal_unit("333333333", [establishment("33333333300033")])], 2),
        "3": page([], 3),
    }
    route = respx.get(REGISTRY_URL).mock(
        side_effect=lambda request: pages[request.url.params["page"]]
    )

    companies = await collect()

    assert [c.siret for c in companies] == [
        "11111111100011",
        "22222222200022",
        "33333333300033",
    ]
    first_params = route.calls[0].request.url.params
    assert first_params["lat"] == "45.764"
    assert first_params["long"] == "4.8357"
    assert first_params["radius"] == "2"
    assert first_params["activite_principale"] == "96.02A,45.20A"
    assert first_params["per_page"] == "25"


@respx.mock
async def test_maps_establishment_fields():
    respx.get(REGISTRY_URL).mock(
        side_effect=[
            page([legal_unit("111111111", [establishment("11111111100011")])], 1),
            page([], 2),
        ]
    )

    [company] = await collect()

    assert company.name == "SALON ECLAT"
    assert company.naf == "96.02A"
    assert company.effectif_code == "01"
    assert company.created_on == date(2015, 3, 1)
    assert company.lat == pytest.approx(45.7655)
    assert company.long == pytest.approx(4.836)
    assert company.address == "12 RUE DE LA REPUBLIQUE 69001 LYON"
    assert company.is_individual is False
    assert company.closed is False


@respx.mock
async def test_skips_closed_and_non_diffusible():
    respx.get(REGISTRY_URL).mock(
        side_effect=[
            page(
                [
                    legal_unit(
                        "111111111",
                        [
                            establishment("11111111100011"),
                            establishment("11111111100029", etat_administratif="F"),
                            establishment(
                                "11111111100037", statut_diffusion_etablissement="P"
                            ),
                        ],
                    ),
                    legal_unit(
                        "222222222",
                        [establishment("22222222200022")],
                        statut_diffusion="P",
                    ),
                    legal_unit(
                        "333333333",
                        [establishment("33333333300033")],
                        etat_administratif="C",
                    ),
                ],
                1,
            ),
            page([], 2),
        ]
    )

    companies = await collect()

    assert [c.siret for c in companies] == ["11111111100011"]
    assert all(c.closed is False for c in companies)


@respx.mock
async def test_marks_companies_opposed_to_prospecting():
    respx.get(REGISTRY_URL).mock(
        side_effect=[
            page(
                [
                    legal_unit(
                        "111111111",
                        [establishment("11111111100011")],
                        opposition_diffusion_commerciale=True,
                    ),
                    legal_unit("222222222", [establishment("22222222200022")]),
                ],
                1,
            ),
            page([], 2),
        ]
    )

    companies = await collect()

    assert {c.siret: c.opposed_to_prospecting for c in companies} == {
        "11111111100011": True,
        "22222222200022": False,
    }


@respx.mock
async def test_retries_on_429(no_real_sleep):
    respx.get(REGISTRY_URL).mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "2"}),
            page([legal_unit("111111111", [establishment("11111111100011")])], 1),
            page([], 2),
        ]
    )

    companies = await collect()

    assert [c.siret for c in companies] == ["11111111100011"]
    assert 2 in no_real_sleep


@respx.mock
async def test_keeps_items_already_yielded_when_api_fails():
    first_page = page([legal_unit("111111111", [establishment("11111111100011")])], 1)
    route = respx.get(REGISTRY_URL).mock(
        side_effect=lambda request: first_page
        if request.url.params["page"] == "1"
        else httpx.Response(500)
    )
    received = []

    with pytest.raises(RegistryUnavailable) as error:
        async for company in fetch_near_point(LYON, NAF):
            received.append(company.siret)

    assert received == ["11111111100011"]
    assert route.call_count == 1 + 4  # page 1, then page 2 tried 4 times (3 retries)
    assert "registre" in str(error.value).lower()


@respx.mock
async def test_radius_over_50km_rejected():
    route = respx.get(REGISTRY_URL)

    with pytest.raises(ValueError):
        await collect_with(Circle(lat=45.764, long=4.8357, radius_km=51))

    assert route.call_count == 0


async def collect_with(circle: Circle) -> list:
    return [company async for company in fetch_near_point(circle, NAF)]


async def test_rate_limiter_spaces_calls(monkeypatch):
    clock = {"now": 100.0}
    pauses: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        pauses.append(seconds)
        clock["now"] += seconds

    monkeypatch.setattr(registry, "_sleep", fake_sleep)
    monkeypatch.setattr(registry, "_monotonic", lambda: clock["now"])
    limiter = RateLimiter(5)

    for _ in range(3):
        await limiter.wait()

    assert sum(pauses) == pytest.approx(0.4)
