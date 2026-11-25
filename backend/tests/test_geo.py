import httpx
import pytest
import respx

from app.domain import Circle
from app.geo import (
    GEO_API_URL,
    CommuneNotFound,
    ZoneTooLarge,
    commune_zone,
    distance_m,
    point_in_zone,
    zone_to_circles,
)

LAT, LONG = 45.764, 4.8357
KM_PER_DEG_LAT = 110.574
KM_PER_DEG_LONG = 111.320 * 0.6976  # cos(45.76°)


def circle_zone(radius_km: float) -> dict:
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [LONG, LAT]},
        "properties": {"radius_km": radius_km},
    }


def square(side_km: float) -> dict:
    dlat = side_km / KM_PER_DEG_LAT
    dlong = side_km / KM_PER_DEG_LONG
    ring = [
        [LONG, LAT],
        [LONG + dlong, LAT],
        [LONG + dlong, LAT + dlat],
        [LONG, LAT + dlat],
        [LONG, LAT],
    ]
    return {"type": "Polygon", "coordinates": [ring]}


def test_circle_zone_returns_itself():
    assert zone_to_circles("circle", circle_zone(3)) == [Circle(lat=LAT, long=LONG, radius_km=3)]


def test_circle_over_50km_raises_zone_too_large():
    with pytest.raises(ZoneTooLarge):
        zone_to_circles("circle", circle_zone(51))


def test_polygon_is_covered_by_circles():
    zone = square(3)

    circles = zone_to_circles("polygon", zone)

    assert len(circles) >= 1
    assert all(c.radius_km == 2 for c in circles)
    ring = zone["coordinates"][0]
    for long, lat in ring[:4]:
        nearest_km = min(distance_m(lat, long, c.lat, c.long) for c in circles) / 1000
        assert nearest_km < 2
    # No gap: every point of a fine grid inside the square is inside some circle.
    for i in range(11):
        for j in range(11):
            lat = ring[0][1] + (ring[2][1] - ring[0][1]) * i / 10
            long = ring[0][0] + (ring[2][0] - ring[0][0]) * j / 10
            nearest_km = min(distance_m(lat, long, c.lat, c.long) for c in circles) / 1000
            assert nearest_km < 2


def test_polygon_wider_than_50km_raises_zone_too_large():
    with pytest.raises(ZoneTooLarge) as error:
        zone_to_circles("polygon", square(55))

    assert "50 km" in str(error.value)


def test_point_in_zone_for_polygon_and_circle():
    inside_lat = LAT + 1.5 / KM_PER_DEG_LAT
    inside_long = LONG + 1.5 / KM_PER_DEG_LONG
    outside_lat = LAT + 4 / KM_PER_DEG_LAT

    assert point_in_zone("polygon", square(3), inside_lat, inside_long)
    assert not point_in_zone("polygon", square(3), outside_lat, inside_long)
    assert point_in_zone("circle", circle_zone(3), inside_lat, inside_long)
    assert not point_in_zone("circle", circle_zone(3), outside_lat, LONG)


def commune_feature(name: str, code: str, departement: str, population: int, score: float):
    return {
        "type": "Feature",
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[4.85, 45.76], [4.92, 45.76], [4.92, 45.79], [4.85, 45.79], [4.85, 45.76]]],
        },
        "properties": {
            "nom": name,
            "code": code,
            "codeDepartement": departement,
            "population": population,
            "_score": score,
        },
    }


@respx.mock
async def test_commune_zone_returns_polygon():
    route = respx.get(GEO_API_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "type": "FeatureCollection",
                "features": [commune_feature("Villeurbanne", "69266", "69", 156928, 1)],
            },
        )
    )

    zone = await commune_zone("Villeurbanne")

    assert zone["type"] == "Feature"
    assert zone["geometry"]["type"] == "Polygon"
    assert zone["properties"] == {"nom": "Villeurbanne", "code": "69266", "codeDepartement": "69"}
    params = route.calls[0].request.url.params
    assert params["nom"] == "Villeurbanne"
    assert params["format"] == "geojson"
    assert params["geometry"] == "contour"
    assert zone_to_circles("commune", zone)


@respx.mock
async def test_commune_zone_by_insee_code():
    route = respx.get(GEO_API_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "type": "FeatureCollection",
                "features": [commune_feature("Villeurbanne", "69266", "69", 156928, 1)],
            },
        )
    )

    await commune_zone("69266")

    params = route.calls[0].request.url.params
    assert params["code"] == "69266"
    assert "nom" not in params


@respx.mock
async def test_commune_zone_homonyms_pick_the_most_populated_best_match():
    respx.get(GEO_API_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "type": "FeatureCollection",
                "features": [
                    commune_feature("Saint-Denis", "11339", "11", 523, 0.298),
                    commune_feature("Saint-Denis", "93066", "93", 149077, 0.298),
                    commune_feature("Saint-Deniscourt", "60571", "60", 80, 0.287),
                ],
            },
        )
    )

    zone = await commune_zone("Saint-Denis")

    assert zone["properties"]["code"] == "93066"


@respx.mock
async def test_unknown_commune_raises():
    respx.get(GEO_API_URL).mock(
        return_value=httpx.Response(200, json={"type": "FeatureCollection", "features": []})
    )

    with pytest.raises(CommuneNotFound) as error:
        await commune_zone("Nullepartville")

    assert "introuvable" in str(error.value)
