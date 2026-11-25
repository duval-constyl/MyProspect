import httpx
import pytest
import respx

from app.domain import JobOffer, RegistryCompany
from app.sources import jobs, registry
from app.sources.jobs import SEARCH_URL, TOKEN_URL, fetch_tech_offers, match_offers_to_companies

ID, SECRET = "id-test", "secret-test"


@pytest.fixture(autouse=True)
def fresh_state(monkeypatch):
    async def no_sleep(seconds: float) -> None:
        return None

    monkeypatch.setattr(registry, "_sleep", no_sleep)  # the shared RateLimiter waits through it
    monkeypatch.setattr(jobs, "_token", None)


def offer_json(offer_id: str, title: str, employer: str | None, postal_code="69003", rome="M1805"):
    data = {
        "id": offer_id,
        "intitule": title,
        "romeCode": rome,
        "lieuTravail": {"libelle": "69 - LYON 03", "codePostal": postal_code, "commune": "69383"},
        "entreprise": {"nom": employer} if employer else {},
    }
    return data


def token_route():
    return respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"access_token": "jeton", "expires_in": 1499})
    )


def company(siret: str, name: str, legal_name: str = "", postal_code: str = "69003") -> RegistryCompany:
    return RegistryCompany(
        siret=siret,
        name=name,
        naf="45.20A",
        effectif_code="12",
        created_on=None,
        lat=45.76,
        long=4.85,
        address=f"12 RUE DES LILAS {postal_code} LYON",
        is_individual=False,
        closed=False,
        legal_name=legal_name,
    )


def offer(employer: str | None, postal_code: str = "69003", offer_id: str = "1") -> JobOffer:
    return JobOffer(
        offer_id=offer_id, title="Développeur web", employer=employer,
        rome_code="M1805", postal_code=postal_code, commune=None,
    )


async def test_returns_false_without_credentials():
    with respx.mock(assert_all_called=False) as mock:
        route = mock.route()

        assert await fetch_tech_offers(["69"], None, None) == []
        assert await fetch_tech_offers(["69"], ID, "") == []

    assert route.call_count == 0


@respx.mock
async def test_true_when_offer_matches_company_and_tech_keywords():
    token_route()
    search = respx.get(SEARCH_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "resultats": [
                    offer_json("A1", "Développeur web full stack (H/F)", "GARAGE MARTIN"),
                    offer_json("A2", "Ingénieur DevOps", "AUTRE ENTREPRISE", rome="M1810"),
                    offer_json("A3", "Technicien informatique", None),
                    offer_json("A4", "Mécanicien automobile", "GARAGE MARTIN", rome="I1604"),
                ]
            },
        )
    )
    companies = [
        company("11111111100011", "GARAGE MARTIN SARL"),
        company("22222222200022", "SALON ECLAT"),
    ]

    offers = await fetch_tech_offers(["69"], ID, SECRET)
    matches = match_offers_to_companies(companies, offers)

    assert [o.offer_id for o in offers] == ["A1", "A2", "A3"]  # the mechanic offer is not technical
    assert set(matches) == {"11111111100011"}
    assert matches["11111111100011"].offer_id == "A1"
    request = search.calls[0].request
    assert request.headers["Authorization"] == "Bearer jeton"
    assert request.url.params["grandDomaine"] == "M18"
    assert request.url.params["departement"] == "69"


@respx.mock
async def test_false_when_api_errors():
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(500))

    assert await fetch_tech_offers(["69"], ID, SECRET) == []


@respx.mock
async def test_search_error_gives_empty_list_not_exception():
    token_route()
    respx.get(SEARCH_URL).mock(side_effect=httpx.ConnectError("hors ligne"))

    assert await fetch_tech_offers(["69"], ID, SECRET) == []


@respx.mock
async def test_token_is_cached_between_searches():
    token = token_route()
    respx.get(SEARCH_URL).mock(return_value=httpx.Response(204))

    await fetch_tech_offers(["69"], ID, SECRET)
    await fetch_tech_offers(["75"], ID, SECRET)

    assert token.call_count == 1
    form = httpx.QueryParams(token.calls[0].request.content.decode())
    assert form["grant_type"] == "client_credentials"
    assert form["scope"] == "api_offresdemploiv2 o2dsoffre"


@respx.mock
async def test_follows_partial_content_pages_and_groups_departements_by_five():
    token_route()
    pages = []

    def answer(request):
        pages.append((request.url.params["departement"], request.url.params["range"]))
        if request.url.params["range"] == "0-149":
            return httpx.Response(206, json={"resultats": [offer_json("P1", "Développeur", "ACME")]})
        return httpx.Response(200, json={"resultats": [offer_json("P2", "Développeur", "ACME")]})

    respx.get(SEARCH_URL).mock(side_effect=answer)

    offers = await fetch_tech_offers(["69", "01", "38", "42", "71", "73"], ID, SECRET)

    assert pages == [
        ("01,38,42,69,71", "0-149"), ("01,38,42,69,71", "150-299"),
        ("73", "0-149"), ("73", "150-299"),
    ]
    assert sorted(o.offer_id for o in offers) == ["P1", "P2"]  # same offers deduplicated


def test_match_uses_legal_name_too():
    companies = [company("11111111100011", "SALON ECLAT", legal_name="ECLAT COIFFURE SARL")]

    matches = match_offers_to_companies(companies, [offer("ECLAT COIFFURE")])

    assert set(matches) == {"11111111100011"}


def test_match_requires_same_departement():
    companies = [company("11111111100011", "GARAGE MARTIN", postal_code="75011")]

    assert match_offers_to_companies(companies, [offer("GARAGE MARTIN", postal_code="69003")]) == {}


def test_match_rejects_distant_names_and_very_short_names():
    companies = [
        company("11111111100011", "GARAGE MARTIN"),
        company("22222222200022", "STE"),
    ]
    offers = [offer("GARAGE DU MARCHE", offer_id="1"), offer("STE", offer_id="2"), offer(None, offer_id="3")]

    assert match_offers_to_companies(companies, offers) == {}
