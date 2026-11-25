from datetime import UTC, datetime

import pytest

from app.models import SiteAnalysisRow
from tests.conftest import PARIS
LYON = (45.764, 4.8357)
FRANCE_BBOX = "-5,41,10,52"
PARIS_BBOX = "2.2,48.8,2.5,48.95"


def names(response) -> list[str]:
    return [item["name"] for item in response.json()["items"]]


def test_list_filters_by_has_site_and_score_min(client, add):
    add("11111111100011", "SALON A", score=75)
    add("22222222200022", "SALON B", score=20, website="https://salon-b.fr")
    add("33333333300033", "SALON C", score=75, phone="0478000003")

    with_site = client.get("/prospects", params={"has_site": "true", "score_min": 10})
    without_site = client.get("/prospects", params={"has_site": "false", "sort": "name"})
    high_score = client.get("/prospects", params={"score_min": 50, "sort": "name"})

    assert names(with_site) == ["SALON B"]
    assert with_site.json()["total"] == 1
    assert names(without_site) == ["SALON A", "SALON C"]
    assert names(high_score) == ["SALON A", "SALON C"]


def test_list_sorted_by_priority_desc(client, add):
    add("11111111100011", "SALON A", score=75)  # 38 + nearby 6 = 44
    add("22222222200022", "SALON B", score=20, phone="01", email="b@b.fr", website="b.fr")  # 10+12+8+6 = 36
    add("33333333300033", "SALON C", score=75, phone="0478000003")  # 38 + 12 + 6 = 56

    response = client.get("/prospects")

    assert names(response) == ["SALON C", "SALON A", "SALON B"]
    assert [item["priority"] for item in response.json()["items"]] == [56, 44, 36]
    ascending = client.get("/prospects", params={"sort": "priority", "order": "asc"})
    assert names(ascending) == ["SALON B", "SALON A", "SALON C"]


def test_list_item_fields(client, add):
    add(
        "11111111100011", "SALON A", score=75, phone="0478000001",
        status="contacted", favorite=True, opposed=True,
    )

    [item] = client.get("/prospects").json()["items"]

    assert item["siret"] == "11111111100011"
    assert item["naf"] == "96.02A"
    assert item["city"] == "PARIS 04"
    assert item["score_web"] == 75
    assert item["tier"] == 5
    assert item["phone"] == "0478000001"
    assert item["email"] is None
    assert item["website"] is None
    assert item["has_site"] is False
    assert (item["status"], item["favorite"]) == ("contacted", True)
    assert item["opposed_to_prospecting"] is True
    assert item["lat"] == pytest.approx(PARIS[0])


def test_search_by_name_and_siret(client, add):
    add("11111111100011", "SALON ECLAT")
    add("22222222200022", "GARAGE MARTIN")

    assert names(client.get("/prospects", params={"q": "eclat"})) == ["SALON ECLAT"]
    assert names(client.get("/prospects", params={"q": "2222222"})) == ["GARAGE MARTIN"]
    assert names(client.get("/prospects", params={"q": "boulangerie"})) == []


def test_list_filters_bbox_naf_status_favorite_and_opposed(client, add):
    add("11111111100011", "PARIS COIFFURE", naf="96.02A", status="contacted", favorite=True)
    add("22222222200022", "LYON GARAGE", LYON, naf="45.20A", opposed=True)
    add("33333333300033", "SANS POSITION", None)

    assert names(client.get("/prospects", params={"bbox": PARIS_BBOX})) == ["PARIS COIFFURE"]
    assert names(client.get("/prospects", params={"naf": "45.20A"})) == ["LYON GARAGE"]
    assert names(client.get("/prospects", params={"status": "contacted"})) == ["PARIS COIFFURE"]
    assert names(client.get("/prospects", params={"status": "new", "sort": "name"})) == [
        "LYON GARAGE",
        "SANS POSITION",
    ]
    assert names(client.get("/prospects", params={"favorite": "true"})) == ["PARIS COIFFURE"]
    assert names(client.get("/prospects", params={"opposed": "true"})) == ["LYON GARAGE"]


def test_list_paginates(client, add):
    for index in range(5):
        add(f"1111111110001{index}", f"SALON {index}")

    page_two = client.get("/prospects", params={"sort": "name", "page": 2, "per_page": 2}).json()

    assert page_two["total"] == 5
    assert [item["name"] for item in page_two["items"]] == ["SALON 2", "SALON 3"]


def test_invalid_bbox_is_rejected_in_french(client):
    response = client.get("/prospects", params={"bbox": "1,2,3"})

    assert response.status_code == 422
    assert "bbox" in response.json()["detail"]


def test_clusters_group_nearby_points_at_low_zoom(client, add):
    add("11111111100011", "PARIS 1", PARIS, score=20)
    add("22222222200022", "PARIS 2", (PARIS[0] + 0.0009, PARIS[1]), score=75)  # 100 m north
    add("33333333300033", "LYON", LYON, score=40)

    low = client.get("/prospects/clusters", params={"bbox": FRANCE_BBOX, "zoom": 5}).json()["clusters"]
    high = client.get("/prospects/clusters", params={"bbox": FRANCE_BBOX, "zoom": 18}).json()["clusters"]

    by_count = sorted(low, key=lambda c: c["count"])
    assert [c["count"] for c in by_count] == [1, 2]
    paris = by_count[1]
    assert paris["max_score"] == 75
    assert paris["tier"] == 5
    assert paris["lat"] == pytest.approx(PARIS[0] + 0.00045, abs=0.001)
    assert paris["prospect_id"] is None
    assert len(high) == 3
    assert all(c["count"] == 1 and c["prospect_id"] for c in high)


def test_stats_counts_with_and_without_site(client, add):
    add("11111111100011", "SALON A", website="https://a.fr")
    add("22222222200022", "SALON B")
    add("33333333300033", "SALON C", website="c.fr")
    add("44444444400044", "LYON", LYON, website="lyon.fr")

    stats = client.get("/prospects/stats", params={"bbox": PARIS_BBOX}).json()

    assert stats == {"in_view": 3, "with_site": 2, "without_site": 1}


def test_detail_for_prospect_without_contacts_or_site(client, add):
    prospect = add("11111111100011", "SALON NU", effectif_code="01")

    response = client.get(f"/prospects/{prospect.id}")

    assert response.status_code == 200
    detail = response.json()
    assert detail["contacts"] == []
    assert detail["site_analysis"] is None
    assert detail["scores"] == []
    assert detail["tracking"] == {"status": "new", "favorite": False, "notes": "", "updated_at": None}
    assert detail["priority"]["value"] == 8 + 6  # small structure + nearby
    assert [r["code"] for r in detail["priority"]["reasons"]] == ["small_structure", "nearby"]


def test_detail_with_contacts_analysis_scores(client, add, db_session):
    prospect = add("11111111100011", "SALON ECLAT", score=20, phone="0478000001", website="https://eclat.fr")
    db_session.add(
        SiteAnalysisRow(
            prospect_id=prospect.id, url="https://eclat.fr/", reachable=True, https=False,
            has_title=True, has_description=True, has_h1=True, has_viewport=True,
            response_ms=150, tech=["wordpress"], mobile_perf=None,
            analyzed_at=datetime(2026, 11, 25, tzinfo=UTC),
        )
    )
    db_session.commit()

    detail = client.get(f"/prospects/{prospect.id}").json()

    assert detail["siret"] == "11111111100011"
    assert detail["opposed_to_prospecting"] is False
    assert {(c["kind"], c["value"], c["source"], c["seen_on"]) for c in detail["contacts"]} == {
        ("phone", "0478000001", "osm", "2026-11-20"),
        ("website", "https://eclat.fr", "osm", "2026-11-20"),
    }
    assert detail["site_analysis"]["https"] is False
    assert detail["site_analysis"]["tech"] == ["wordpress"]
    assert detail["scores"] == [
        {"offer": "web", "value": 20, "tier": 2,
         "reasons": [{"code": "no_site", "label": "Aucun site web connu", "points": 20}]}
    ]
    assert detail["priority"]["value"] == 10 + 12 + 6
    assert sum(r["points"] for r in detail["priority"]["reasons"]) == detail["priority"]["value"]


def test_detail_unknown_id_404(client, db_session):
    response = client.get("/prospects/999999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Prospect introuvable."
