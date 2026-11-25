"""Zone geometry: zone -> circles for the registry, point-in-zone, commune contours.

Zone GeoJSON conventions:
- circle: a Feature whose geometry is a Point [long, lat] and whose properties hold
  `radius_km`;
- polygon and commune: a Polygon/MultiPolygon geometry, or a Feature holding one.
"""

import math
import re

import httpx
import shapely
from shapely import Point
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry

from app.domain import Circle

MAX_ZONE_WIDTH_KM = 50
MAX_CIRCLE_RADIUS_KM = 50
COVER_RADIUS_KM = 2
# Grid step so that every point of a cell is strictly inside the cell's circle
# (half-diagonal = 0.95 * radius), with a margin for the flat-earth approximation.
GRID_STEP_KM = COVER_RADIUS_KM * math.sqrt(2) * 0.95
KM_PER_DEG_LAT = 110.574
KM_PER_DEG_LONG_AT_EQUATOR = 111.320

GEO_API_URL = "https://geo.api.gouv.fr/communes"
INSEE_CODE = re.compile(r"\d{5}|2[AB]\d{3}", re.IGNORECASE)
TIMEOUT_S = 15.0


class ZoneTooLarge(ValueError):
    """The zone is wider than what one collection may cover."""


class CommuneNotFound(ValueError):
    """No commune matches the given name or INSEE code."""


def zone_to_circles(kind: str, geojson: dict) -> list[Circle]:
    if kind == "circle":
        return [_circle(geojson)]
    if kind not in ("polygon", "commune"):
        raise ValueError(f"Type de zone inconnu : « {kind} ».")

    area = _area(geojson)
    min_long, min_lat, max_long, max_lat = area.bounds
    km_per_deg_long = KM_PER_DEG_LONG_AT_EQUATOR * math.cos(math.radians((min_lat + max_lat) / 2))
    width_km = (max_long - min_long) * km_per_deg_long
    height_km = (max_lat - min_lat) * KM_PER_DEG_LAT
    largest_km = max(width_km, height_km)
    if largest_km > MAX_ZONE_WIDTH_KM:
        raise ZoneTooLarge(
            f"Zone trop grande : {largest_km:.0f} km de large, {MAX_ZONE_WIDTH_KM} km maximum."
        )

    # Flat projection in km around the zone (enough below 50 km).
    def to_km(coords):  # (N, 2) array of [long, lat]
        return (coords - (min_long, min_lat)) * (km_per_deg_long, KM_PER_DEG_LAT)

    projected = shapely.transform(area, to_km)
    circles = []
    for y in _grid_axis(height_km):
        for x in _grid_axis(width_km):
            if projected.distance(Point(x, y)) <= COVER_RADIUS_KM:
                circles.append(
                    Circle(
                        lat=min_lat + y / KM_PER_DEG_LAT,
                        long=min_long + x / km_per_deg_long,
                        radius_km=COVER_RADIUS_KM,
                    )
                )
    return circles


def point_in_zone(kind: str, geojson: dict, lat: float, long: float) -> bool:
    if kind == "circle":
        circle = _circle(geojson)
        return distance_m(lat, long, circle.lat, circle.long) <= circle.radius_km * 1000
    return _area(geojson).covers(Point(long, lat))


async def commune_zone(name_or_code: str, client: httpx.AsyncClient | None = None) -> dict:
    """Contour of a commune as a GeoJSON Feature (properties: nom, code, codeDepartement).

    A 5-character value is read as an INSEE code. For a name, homonyms with the
    same best score are settled by population (the largest wins).
    """
    query = name_or_code.strip()
    params = {
        "fields": "nom,code,codeDepartement,population",
        "format": "geojson",
        # Without `geometry=contour` the API returns the centre point.
        "geometry": "contour",
    }
    if INSEE_CODE.fullmatch(query):
        params["code"] = query.upper()
    else:
        params["nom"] = query

    own_client = client is None
    http = client or httpx.AsyncClient(timeout=TIMEOUT_S)
    try:
        response = await http.get(GEO_API_URL, params=params)
        response.raise_for_status()
        features = response.json().get("features") or []
    finally:
        if own_client:
            await http.aclose()

    features = [f for f in features if (f.get("geometry") or {}).get("type") in ("Polygon", "MultiPolygon")]
    if not features:
        raise CommuneNotFound(f"Commune introuvable : « {query} ».")
    best_score = max(_score(f) for f in features)
    best = [f for f in features if math.isclose(_score(f), best_score)]
    chosen = max(best, key=lambda f: f["properties"].get("population") or 0)
    return {
        "type": "Feature",
        "geometry": chosen["geometry"],
        "properties": {key: chosen["properties"].get(key) for key in ("nom", "code", "codeDepartement")},
    }


def distance_m(lat1: float, long1: float, lat2: float, long2: float) -> float:
    """Great-circle distance in metres (haversine)."""
    earth_radius_m = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = phi2 - phi1
    d_lambda = math.radians(long2 - long1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * earth_radius_m * math.asin(math.sqrt(a))


def _grid_axis(length_km: float) -> list[float]:
    """Cell centres along one axis, centred on the zone so the margins are equal."""
    count = max(1, math.ceil(length_km / GRID_STEP_KM))
    start = (length_km - (count - 1) * GRID_STEP_KM) / 2
    return [start + i * GRID_STEP_KM for i in range(count)]


def _split_feature(geojson: dict) -> tuple[dict, dict]:
    if geojson.get("type") == "Feature":
        return geojson.get("geometry") or {}, geojson.get("properties") or {}
    return geojson, {}


def _circle(geojson: dict) -> Circle:
    geometry, properties = _split_feature(geojson)
    try:
        if geometry.get("type") != "Point":
            raise ValueError
        long, lat = (float(v) for v in geometry["coordinates"][:2])
        radius_km = float(properties["radius_km"])
    except (KeyError, TypeError, ValueError):
        raise ValueError("Cercle invalide : centre (Point) et rayon `radius_km` attendus.") from None
    if radius_km <= 0:
        raise ValueError("Cercle invalide : le rayon doit être positif.")
    if radius_km > MAX_CIRCLE_RADIUS_KM:
        raise ZoneTooLarge(
            f"Zone trop grande : rayon de {radius_km:g} km, {MAX_CIRCLE_RADIUS_KM} km maximum."
        )
    return Circle(lat=lat, long=long, radius_km=radius_km)


def _area(geojson: dict) -> BaseGeometry:
    geometry, _ = _split_feature(geojson)
    try:
        area = shape(geometry)
    except (AttributeError, KeyError, TypeError, ValueError, IndexError):
        raise ValueError("Zone invalide : polygone GeoJSON attendu.") from None
    if area.geom_type not in ("Polygon", "MultiPolygon") or area.is_empty:
        raise ValueError("Zone invalide : polygone GeoJSON attendu.")
    return area


def _score(feature: dict) -> float:
    return float(feature.get("properties", {}).get("_score", 1))
