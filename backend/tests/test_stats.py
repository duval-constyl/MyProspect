from datetime import UTC, datetime

from app.models import OutreachDraft, Zone
from tests.conftest import PARIS

LYON = (45.764, 4.8357)
PARIS_CIRCLE = {
    "type": "Feature",
    "geometry": {"type": "Point", "coordinates": [PARIS[1], PARIS[0]]},
    "properties": {"radius_km": 1},
}


def draft(session, prospect, offer="web", variant="template:v1", created_at=None):
    row = OutreachDraft(
        prospect_id=prospect.id, offer=offer, channel="email", subject="Objet", body="Bonjour",
        source="template", variant=variant,
    )
    if created_at is not None:
        row.created_at = created_at
    session.add(row)
    session.commit()


def stats(client, group_by):
    response = client.get("/stats/outreach", params={"group_by": group_by})
    assert response.status_code == 200
    return response.json()


def by_key(rows):
    return {row["key"]: row for row in rows}


def test_reply_rate_by_offer(client, db_session, add):
    replied = add("11111111100011", "SALON UN", status="replied")
    contacted = add("22222222200022", "SALON DEUX", status="contacted")
    refused = add("33333333300033", "SALON TROIS", status="refused")
    not_yet = add("44444444400044", "SALON QUATRE", status="new")
    add("55555555500055", "SALON CINQ", status="to_contact")  # no draft, not contacted: left out
    draft(db_session, replied, "web")
    draft(db_session, contacted, "web")
    draft(db_session, refused, "mobile")
    draft(db_session, not_yet, "mobile")

    rows = stats(client, "offer")

    assert [row["key"] for row in rows] == ["web", "mobile"]
    assert by_key(rows)["web"] == {"key": "web", "contacted": 2, "replied": 1, "refused": 0, "reply_rate": 0.5}
    assert by_key(rows)["mobile"] == {"key": "mobile", "contacted": 1, "replied": 0, "refused": 1, "reply_rate": 0.0}


def test_group_by_variant(client, db_session, add):
    both = add("11111111100011", "SALON UN", status="replied")
    other = add("22222222200022", "SALON DEUX", status="contacted")
    # The latest draft is the one most likely sent: it decides the variant (and the offer).
    draft(db_session, both, "web", "template:v1", created_at=datetime(2026, 11, 1, tzinfo=UTC))
    draft(db_session, both, "mobile", "llm:claude-opus-5-5:v1", created_at=datetime(2026, 11, 2, tzinfo=UTC))
    draft(db_session, other, "web", "template:v1")

    rows = by_key(stats(client, "variant"))

    assert rows["llm:claude-opus-5-5:v1"] == {
        "key": "llm:claude-opus-5-5:v1", "contacted": 1, "replied": 1, "refused": 0, "reply_rate": 1.0,
    }
    assert rows["template:v1"] == {"key": "template:v1", "contacted": 1, "replied": 0, "refused": 0, "reply_rate": 0.0}
    assert by_key(stats(client, "offer"))["mobile"]["replied"] == 1


def test_zero_contacted_gives_rate_0_not_division_error(client, db_session, add):
    prospect = add("11111111100011", "SALON UN", status="new")
    draft(db_session, prospect, "web")
    db_session.add(Zone(kind="circle", geojson=PARIS_CIRCLE, naf_codes=["96.02A"]))
    db_session.commit()

    assert stats(client, "offer") == [{"key": "web", "contacted": 0, "replied": 0, "refused": 0, "reply_rate": 0.0}]
    zones = stats(client, "zone")
    assert len(zones) == 1
    assert zones[0]["contacted"] == 0
    assert zones[0]["reply_rate"] == 0.0


def test_prospect_without_draft_counted_under_variant_none(client, db_session, add):
    add("11111111100011", "SALON UN", status="contacted")

    assert stats(client, "variant") == [{"key": "none", "contacted": 1, "replied": 0, "refused": 0, "reply_rate": 0.0}]
    assert by_key(stats(client, "offer"))["none"]["contacted"] == 1


def test_group_by_zone(client, db_session, add):
    zone = Zone(kind="circle", geojson=PARIS_CIRCLE, naf_codes=["96.02A"])
    db_session.add(zone)
    db_session.commit()
    add("11111111100011", "SALON PARIS", PARIS, status="replied")
    add("22222222200022", "SALON LYON", LYON, status="contacted")
    add("33333333300033", "SALON SANS POSITION", None, status="refused")

    rows = stats(client, "zone")

    assert [row["key"] for row in rows] == [str(zone.id), "none"]
    assert rows[0] == {"key": str(zone.id), "contacted": 1, "replied": 1, "refused": 0, "reply_rate": 1.0}
    assert rows[1] == {"key": "none", "contacted": 2, "replied": 0, "refused": 1, "reply_rate": 0.0}


def test_unknown_group_by_is_rejected(client):
    assert client.get("/stats/outreach", params={"group_by": "city"}).status_code == 422
