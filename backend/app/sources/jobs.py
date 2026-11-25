"""Technical job offers from France Travail (« Offres d'emploi v2 ») and approximate
matching with the collected companies (V2 plan, Task 4).

Study of 2026-11-25: the search has no company or SIRET filter. So the offers of the
IT field (grandDomaine M18) are fetched per département of the zone, then their
employer name is compared with each company's sign and legal name, in the same
département. Approximate by nature: anonymous offers and recruitment agencies never
match. Any failure gives an empty list: the « hiring » bonus is simply not given.
"""

import logging
import re
import time
from collections.abc import Iterable
from difflib import SequenceMatcher

import httpx

from app.domain import JobOffer, RegistryCompany
from app.http import new_http_client
from app.sources.osm import normalize_name
from app.sources.registry import RateLimiter

logger = logging.getLogger(__name__)

TOKEN_URL = "https://entreprise.francetravail.fr/connexion/oauth2/access_token?realm=%2Fpartenaire"
SEARCH_URL = "https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search"
SCOPE = "api_offresdemploiv2 o2dsoffre"
TECH_DOMAIN = "M18"  # « Informatique / Télécommunication »
TECH_KEYWORDS = ("developpeur", "informatique", "devops")
PAGE_SIZE = 150
MAX_RANGE_START = 1000  # the API serves at most 1,150 offers per search
DEPARTEMENTS_PER_SEARCH = 5
MIN_NAME_SIMILARITY = 0.85  # stricter than OSM: there is no distance to confirm the match
MIN_NAME_LENGTH = 4
TIMEOUT_S = 30.0
POSTAL_CODE = re.compile(r"\b(\d{5})\b")

_token: tuple[str, float] | None = None  # (access token, expiry on the monotonic clock)
_monotonic = time.monotonic
_limiter = RateLimiter(3)


async def fetch_tech_offers(
    departements: Iterable[str],
    client_id: str | None,
    client_secret: str | None,
    client: httpx.AsyncClient | None = None,
) -> list[JobOffer]:
    """Open IT job offers of the given départements; [] without credentials or on any error."""
    if not client_id or not client_secret:
        return []
    codes = sorted({code for code in departements if code})
    if not codes:
        return []

    own_client = client is None
    http = client or new_http_client(timeout=TIMEOUT_S)
    try:
        token = await _access_token(http, client_id, client_secret)
        offers: dict[str, JobOffer] = {}
        for start in range(0, len(codes), DEPARTEMENTS_PER_SEARCH):
            for offer in await _search(http, token, codes[start : start + DEPARTEMENTS_PER_SEARCH]):
                offers.setdefault(offer.offer_id, offer)
        return [offer for offer in offers.values() if _is_technical(offer)]
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        logger.warning("Offres d'emploi France Travail indisponibles : %s", type(exc).__name__)
        return []
    finally:
        if own_client:
            await http.aclose()


async def _access_token(http: httpx.AsyncClient, client_id: str, client_secret: str) -> str:
    global _token
    if _token and _token[1] > _monotonic():
        return _token[0]
    response = await http.post(
        TOKEN_URL,
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": SCOPE,
        },
    )
    response.raise_for_status()
    payload = response.json()
    lifetime = max(0, int(payload.get("expires_in", 0)) - 60)  # renew a minute early
    _token = (payload["access_token"], _monotonic() + lifetime)
    return _token[0]


async def _search(http: httpx.AsyncClient, token: str, departements: list[str]) -> list[JobOffer]:
    offers: list[JobOffer] = []
    start = 0
    while start <= MAX_RANGE_START:
        await _limiter.wait()
        response = await http.get(
            SEARCH_URL,
            params={
                "grandDomaine": TECH_DOMAIN,
                "departement": ",".join(departements),
                "range": f"{start}-{start + PAGE_SIZE - 1}",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        if response.status_code == 204:  # nothing (more) to read
            break
        response.raise_for_status()
        offers.extend(
            offer for offer in map(_to_offer, response.json().get("resultats") or []) if offer
        )
        if response.status_code != 206:  # 206 = partial content, more pages exist
            break
        start += PAGE_SIZE
    return offers


def _to_offer(data: dict) -> JobOffer | None:
    if not data.get("id"):
        return None
    place = data.get("lieuTravail") or {}
    employer = ((data.get("entreprise") or {}).get("nom") or "").strip() or None
    return JobOffer(
        offer_id=str(data["id"]),
        title=data.get("intitule") or "",
        employer=employer,
        rome_code=data.get("romeCode"),
        postal_code=place.get("codePostal"),
        commune=place.get("commune"),
    )


def _is_technical(offer: JobOffer) -> bool:
    title = normalize_name(offer.title)
    return (offer.rome_code or "").startswith(TECH_DOMAIN) or any(word in title for word in TECH_KEYWORDS)


def match_offers_to_companies(
    companies: list[RegistryCompany], offers: list[JobOffer]
) -> dict[str, JobOffer]:
    """SIRET -> one technical offer whose employer looks like the company, in its département."""
    matches: dict[str, JobOffer] = {}
    for company in companies:
        departement = departement_of_address(company.address)
        names = [n for n in {normalize_name(company.name), normalize_name(company.legal_name)} if len(n) >= MIN_NAME_LENGTH]
        if not departement or not names:
            continue
        best: tuple[float, JobOffer] | None = None
        for offer in offers:
            employer = normalize_name(offer.employer or "")
            if len(employer) < MIN_NAME_LENGTH or _departement_of_offer(offer) != departement:
                continue
            similarity = max(SequenceMatcher(None, name, employer).ratio() for name in names)
            if similarity >= MIN_NAME_SIMILARITY and (best is None or similarity > best[0]):
                best = (similarity, offer)
        if best:
            matches[company.siret] = best[1]
    return matches


def _departement_of_postal_code(postal_code: str | None) -> str | None:
    if not postal_code or len(postal_code) != 5 or not postal_code.isdigit():
        return None
    return postal_code[:3] if postal_code.startswith("97") else postal_code[:2]


def departement_of_address(address: str) -> str | None:
    match = POSTAL_CODE.search(address or "")
    return _departement_of_postal_code(match.group(1)) if match else None


def _departement_of_offer(offer: JobOffer) -> str | None:
    by_postal_code = _departement_of_postal_code(offer.postal_code)
    if by_postal_code:
        return by_postal_code
    commune = (offer.commune or "").upper()
    if commune[:2] in ("2A", "2B"):
        return "20"  # Corsican INSEE codes; postal codes start with 20
    return _departement_of_postal_code(commune)
