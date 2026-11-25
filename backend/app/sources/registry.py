"""Client for the official company registry (API Recherche d'entreprises).

Endpoint verified on 2026-11-25 (OpenAPI at /openapi.json): `near_point` takes
lat, long, radius (km, max 50), activite_principale (comma-separated NAF codes),
page and per_page (max 25). Companies are legal units; the establishments located
in the circle are in `matching_etablissements`.
"""

import asyncio
import time
from collections.abc import AsyncIterator
from datetime import date

import httpx

from app.domain import Circle, RegistryCompany
from app.http import new_http_client

REGISTRY_URL = "https://recherche-entreprises.api.gouv.fr/near_point"
MAX_RADIUS_KM = 50
PER_PAGE = 25  # API maximum
MATCHING_ESTABLISHMENTS_LIMIT = 100  # API maximum (default 10)
RETRIES = 3
TIMEOUT_S = 20.0

# Indirections so tests can replace time without waiting.
_sleep = asyncio.sleep
_monotonic = time.monotonic


class RegistryUnavailable(Exception):
    """The registry kept failing after every retry."""


class RateLimiter:
    """Spaces calls so that at most `per_second` start in any second."""

    def __init__(self, per_second: int) -> None:
        self._interval = 1.0 / per_second
        self._next_slot = 0.0
        self._lock = asyncio.Lock()

    async def wait(self) -> None:
        async with self._lock:
            now = _monotonic()
            if self._next_slot > now:
                await _sleep(self._next_slot - now)
                now = self._next_slot
            self._next_slot = now + self._interval


# Shared by every collection: the registry allows 7 calls/s, we stay at 5.
_limiter = RateLimiter(5)


async def fetch_near_point(
    circle: Circle,
    naf_codes: list[str],
    client: httpx.AsyncClient | None = None,
) -> AsyncIterator[RegistryCompany]:
    """Yield the open, publicly listed establishments of the circle, page by page.

    Items already yielded stay valid if a later page fails: the error
    (RegistryUnavailable) is raised only when that page is reached.
    """
    if circle.radius_km > MAX_RADIUS_KM:
        raise ValueError(f"Rayon de {circle.radius_km} km refusé : {MAX_RADIUS_KM} km maximum.")

    own_client = client is None
    http = client or new_http_client(timeout=TIMEOUT_S)
    try:
        page = 1
        while True:
            payload = await _get_page(http, circle, naf_codes, page)
            results = payload.get("results") or []
            if not results:
                return
            for legal_unit in results:
                for company in _companies_of(legal_unit):
                    yield company
            total_pages = payload.get("total_pages")
            if total_pages is not None and page >= total_pages:
                return
            page += 1
    finally:
        if own_client:
            await http.aclose()


async def _get_page(
    http: httpx.AsyncClient, circle: Circle, naf_codes: list[str], page: int
) -> dict:
    params: dict[str, str | int | float] = {
        "lat": circle.lat,
        "long": circle.long,
        "radius": _format_radius(circle.radius_km),
        "page": page,
        "per_page": PER_PAGE,
        "limite_matching_etablissements": MATCHING_ESTABLISHMENTS_LIMIT,
    }
    if naf_codes:
        params["activite_principale"] = ",".join(naf_codes)

    problem = ""
    for attempt in range(RETRIES + 1):
        await _limiter.wait()
        try:
            response = await http.get(REGISTRY_URL, params=params)
        except httpx.HTTPError as exc:
            problem = f"erreur réseau ({type(exc).__name__})"
            retry_after = None
        else:
            if response.status_code == 200:
                return response.json()
            problem = f"HTTP {response.status_code}"
            if response.status_code != 429 and response.status_code < 500:
                break  # a client error will not fix itself
            retry_after = _retry_after(response)
        if attempt < RETRIES:
            await _sleep(retry_after if retry_after is not None else 2**attempt)

    raise RegistryUnavailable(
        f"Registre des entreprises indisponible ({problem}) pour la page {page}."
    )


def _format_radius(radius_km: float) -> str:
    return f"{radius_km:g}"


def _retry_after(response: httpx.Response) -> float | None:
    try:
        return float(response.headers["Retry-After"])
    except (KeyError, ValueError):
        return None


def _companies_of(legal_unit: dict) -> list[RegistryCompany]:
    if legal_unit.get("statut_diffusion") != "O":
        return []
    if legal_unit.get("etat_administratif") != "A":
        return []

    companies = []
    for establishment in legal_unit.get("matching_etablissements") or []:
        if establishment.get("statut_diffusion_etablissement") != "O":
            continue
        if establishment.get("etat_administratif") != "A":
            continue
        companies.append(_to_company(legal_unit, establishment))
    return companies


def _to_company(legal_unit: dict, establishment: dict) -> RegistryCompany:
    complements = legal_unit.get("complements") or {}
    is_individual = complements.get("est_entrepreneur_individuel")
    if is_individual is None:
        is_individual = legal_unit.get("nature_juridique") == "1000"
    return RegistryCompany(
        siret=establishment["siret"],
        name=_display_name(legal_unit, establishment),
        naf=establishment.get("activite_principale") or legal_unit.get("activite_principale") or "",
        # Company-level size and age: they describe the business behind the shop.
        effectif_code=legal_unit.get("tranche_effectif_salarie"),
        created_on=_parse_date(legal_unit.get("date_creation")),
        lat=_parse_float(establishment.get("latitude")),
        long=_parse_float(establishment.get("longitude")),
        address=establishment.get("adresse") or "",
        is_individual=bool(is_individual),
        closed=False,
        opposed_to_prospecting=legal_unit.get("opposition_diffusion_commerciale") is True,
    )


def _display_name(legal_unit: dict, establishment: dict) -> str:
    """The shop sign first (what people and OpenStreetMap know), then the legal name."""
    signs = establishment.get("liste_enseignes") or []
    return signs[0] if signs else (
        establishment.get("nom_commercial") or legal_unit.get("nom_complet") or ""
    )


def _parse_float(value: object) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _parse_date(value: object) -> date | None:
    try:
        return date.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        return None
