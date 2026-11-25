"""OpenStreetMap enrichment through the Overpass API, and matching with the registry.

Usage policy of the main instance (OSM wiki, checked 2026-11-25): identify the app
with a User-Agent, no parallel queries, pause 30 s after an HTTP 429 or 406,
stay well under 10,000 queries a day (under 100 for regular use).
OpenStreetMap data is optional enrichment: any failure yields an empty list.
"""

import asyncio
import logging
import math
import re
import time
import unicodedata
from difflib import SequenceMatcher

import httpx

from app.domain import Circle, OsmBusiness, RegistryCompany

logger = logging.getLogger(__name__)

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
USER_AGENT = "MyProspect/0.1 (outil local de prospection B2B, usage personnel)"
ELEMENT_KEYS = ("shop", "amenity", "craft", "office")
QUERY_TIMEOUT_S = 25
HTTP_TIMEOUT_S = 40.0
BACKOFF_AFTER_REFUSAL_S = 30.0
MIN_NAME_SIMILARITY = 0.6

LEGAL_FORMS = {
    "sarl", "sas", "sasu", "eurl", "sa", "snc", "sci", "scop", "scp", "sel",
    "selarl", "selas", "ei", "eirl", "earl", "gie", "sca", "scs",
}

# Indirections so tests can replace time without waiting.
_sleep = asyncio.sleep
_monotonic = time.monotonic
_blocked_until = 0.0


def build_query(circle: Circle) -> str:
    around = f"(around:{round(circle.radius_km * 1000)},{circle.lat},{circle.long})"
    selectors = "".join(f'nwr["{key}"]["name"]{around};' for key in ELEMENT_KEYS)
    return f"[out:json][timeout:{QUERY_TIMEOUT_S}];({selectors});out center tags;"


async def fetch_osm_businesses(
    circle: Circle, client: httpx.AsyncClient | None = None
) -> list[OsmBusiness]:
    """Named shops, amenities, crafts and offices of the circle; [] on any failure."""
    global _blocked_until
    wait = _blocked_until - _monotonic()
    if wait > 0:
        await _sleep(wait)

    own_client = client is None
    http = client or httpx.AsyncClient(timeout=HTTP_TIMEOUT_S)
    try:
        response = await http.post(
            OVERPASS_URL,
            data={"data": build_query(circle)},
            headers={"User-Agent": USER_AGENT},
        )
        if response.status_code in (406, 429):
            _blocked_until = _monotonic() + BACKOFF_AFTER_REFUSAL_S
        if response.status_code != 200:
            logger.warning("Overpass a répondu HTTP %s", response.status_code)
            return []
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Overpass indisponible : %s", type(exc).__name__)
        return []
    finally:
        if own_client:
            await http.aclose()

    remark = payload.get("remark") or ""
    if "error" in remark.lower():
        logger.warning("Overpass a interrompu la requête : %s", remark)
        return []
    return [b for b in map(_to_business, payload.get("elements") or []) if b is not None]


def _to_business(element: dict) -> OsmBusiness | None:
    tags = element.get("tags") or {}
    position = element if "lat" in element else element.get("center") or {}
    name = tags.get("name")
    if not name or "lat" not in position or "lon" not in position:
        return None
    return OsmBusiness(
        osm_id=f"{element.get('type')}/{element.get('id')}",
        name=name,
        lat=float(position["lat"]),
        long=float(position["lon"]),
        phone=_first(tags, "phone", "contact:phone"),
        email=_first(tags, "email", "contact:email"),
        website=_first(tags, "website", "contact:website"),
    )


def _first(tags: dict, *keys: str) -> str | None:
    """First non-empty value; OSM separates multiple values with ';'."""
    for key in keys:
        value = (tags.get(key) or "").split(";")[0].strip()
        if value:
            return value
    return None


def match_osm_to_registry(
    companies: list[RegistryCompany],
    osm: list[OsmBusiness],
    max_distance_m: int = 80,
) -> dict[str, OsmBusiness]:
    """Pair each company with at most one OSM business, and each business with one company.

    A pair needs both a distance <= max_distance_m and a normalized-name
    similarity >= 0.6. Best similarity wins, then the nearest.
    """
    candidates = []
    for company in companies:
        if company.lat is None or company.long is None:
            continue
        company_name = normalize_name(company.name)
        for index, place in enumerate(osm):
            distance = distance_m(company.lat, company.long, place.lat, place.long)
            if distance > max_distance_m:
                continue
            similarity = SequenceMatcher(None, company_name, normalize_name(place.name)).ratio()
            if similarity >= MIN_NAME_SIMILARITY:
                candidates.append((-similarity, distance, company.siret, index))

    matches: dict[str, OsmBusiness] = {}
    used: set[int] = set()
    for _, _, siret, index in sorted(candidates):
        if siret not in matches and index not in used:
            matches[siret] = osm[index]
            used.add(index)
    return matches


def normalize_name(name: str) -> str:
    """Lowercase, no accents, no punctuation, no legal form."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    words = re.sub(r"[^a-z0-9]+", " ", ascii_name.lower()).split()
    return " ".join(word for word in words if word not in LEGAL_FORMS)


def distance_m(lat1: float, long1: float, lat2: float, long2: float) -> float:
    """Great-circle distance in metres (haversine)."""
    earth_radius_m = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = phi2 - phi1
    d_lambda = math.radians(long2 - long1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * earth_radius_m * math.asin(math.sqrt(a))
