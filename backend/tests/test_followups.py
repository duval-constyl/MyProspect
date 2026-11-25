from datetime import UTC, date, datetime

import pytest
from sqlalchemy import select

from app.models import Contact, FollowUp, Tracking, TrackingEvent
from app.routers.followups import get_now, paris_today

# 25 November 2026, 10:00 in Paris.
NOW = datetime(2026, 11, 25, 9, 0, tzinfo=UTC)


@pytest.fixture
def clock(client):
    current = {"now": NOW}
    client.app.dependency_overrides[get_now] = lambda: current["now"]
    yield current
    client.app.dependency_overrides.pop(get_now, None)


def plan_followup(client, prospect_id: int, due_on: str, note: str = "Rappeler") -> dict:
    response = client.post(f"/prospects/{prospect_id}/followups", json={"due_on": due_on, "note": note})
    assert response.status_code == 201, response.text
    return response.json()


def test_followup_due_today_appears_once(client, add, db_session, clock):
    prospect = add("11111111100011", "SALON A", phone="0478000001", email="a@a.fr", website="a.fr")
    plan_followup(client, prospect.id, "2026-11-25", "Rappeler pour le devis")

    today = client.get("/today").json()

    assert [(f["prospect_id"], f["due_on"], f["note"]) for f in today["followups_due"]] == [
        (prospect.id, "2026-11-25", "Rappeler pour le devis")
    ]
    item = today["followups_due"][0]
    assert item["prospect_name"] == "SALON A"
    assert item["phone"] == "0478000001"


def test_past_due_followup_appears_in_today(client, add, clock):
    prospect = add("11111111100011", "SALON A")
    plan_followup(client, prospect.id, "2026-11-20", "En retard")
    plan_followup(client, prospect.id, "2026-12-01", "Plus tard")

    due = client.get("/today").json()["followups_due"]

    assert [f["note"] for f in due] == ["En retard"]


def test_done_followup_disappears(client, add, clock):
    prospect = add("11111111100011", "SALON A")
    followup = plan_followup(client, prospect.id, "2026-11-25")

    done = client.post(f"/followups/{followup['id']}/done")

    assert done.status_code == 200
    assert done.json()["done_at"]
    assert client.get("/today").json()["followups_due"] == []
    assert client.post("/followups/999999/done").status_code == 404


def test_due_date_uses_paris_calendar_day(client, add, clock):
    # Paris is UTC+1 in November: 23:30 UTC on the 24th is 00:30 on the 25th in Paris.
    # (The plan's example, 21:30 UTC, would still be the 24th in Paris: 22:30.)
    clock["now"] = datetime(2026, 11, 24, 23, 30, tzinfo=UTC)
    prospect = add("11111111100011", "SALON A")
    plan_followup(client, prospect.id, "2026-11-25", "Le 25 à Paris")
    plan_followup(client, prospect.id, "2026-11-26", "Le 26")

    assert paris_today(clock["now"]) == date(2026, 11, 25)
    assert [f["note"] for f in client.get("/today").json()["followups_due"]] == ["Le 25 à Paris"]


def test_paris_day_around_daylight_saving_change():
    # Night of 28 to 29 March 2026: clocks go from 02:00 to 03:00 in Paris.
    assert paris_today(datetime(2026, 3, 28, 22, 59, tzinfo=UTC)) == date(2026, 3, 28)
    assert paris_today(datetime(2026, 3, 28, 23, 0, tzinfo=UTC)) == date(2026, 3, 29)
    # Summer time: UTC+2, so 22:00 UTC is already the next day.
    assert paris_today(datetime(2026, 6, 30, 22, 0, tzinfo=UTC)) == date(2026, 7, 1)


def test_status_change_writes_event(client, add, db_session):
    prospect = add("11111111100011", "SALON A")

    client.patch(f"/prospects/{prospect.id}/tracking", json={"status": "contacted"})
    client.patch(f"/prospects/{prospect.id}/tracking", json={"notes": "A répondu par mail"})
    client.patch(f"/prospects/{prospect.id}/tracking", json={"favorite": True})
    client.post(f"/prospects/{prospect.id}/do-not-contact")

    events = db_session.scalars(
        select(TrackingEvent).where(TrackingEvent.prospect_id == prospect.id).order_by(TrackingEvent.id)
    ).all()
    assert [(e.kind, e.text) for e in events] == [
        ("status", "Statut : Contacté"),
        ("note", "A répondu par mail"),
        ("status", "Statut : Refusé (ne plus contacter)"),
    ]


def test_followup_creation_and_completion_write_events(client, add, db_session, clock):
    prospect = add("11111111100011", "SALON A")
    followup = plan_followup(client, prospect.id, "2026-11-28", "Envoyer le devis")
    client.post(f"/followups/{followup['id']}/done")

    texts = db_session.scalars(
        select(TrackingEvent.text).where(TrackingEvent.kind == "followup").order_by(TrackingEvent.id)
    ).all()
    assert texts == ["Relance prévue le 28/11/2026 : Envoyer le devis", "Relance faite : Envoyer le devis"]


def test_top_priority_excludes_contacted_and_refused(client, add, clock):
    add("11111111100011", "NOUVEAU", score=75)
    add("22222222200022", "CONTACTE", score=75, status="contacted")
    add("33333333300033", "REFUSE", score=75, status="refused")
    add("44444444400044", "A REPONDU", score=75, status="replied")
    add("55555555500055", "A CONTACTER", score=20, status="to_contact")

    top = client.get("/today").json()["top_priority"]

    assert [p["name"] for p in top] == ["NOUVEAU", "A CONTACTER"]
    assert top[0]["best_offer"] == "web"
    assert top[0]["priority"] >= top[1]["priority"]


def test_top_priority_keeps_twenty_and_uses_the_best_offer(client, add, db_session, clock):
    from tests.test_multi_offer import add_score

    for index in range(22):
        add(f"1111111110{index:04d}", f"SALON {index:02d}", score=index)
    mobile_star = add("99999999900099", "MOBILE STAR", score=0)
    add_score(db_session, mobile_star.id, "mobile", 90)

    top = client.get("/today").json()["top_priority"]

    assert len(top) == 20
    assert top[0]["name"] == "MOBILE STAR"
    assert top[0]["best_offer"] == "mobile"


def test_create_followup_validations(client, add, clock):
    prospect = add("11111111100011", "SALON A")

    assert client.post("/prospects/999999/followups", json={"due_on": "2026-11-25"}).status_code == 404
    assert client.post(f"/prospects/{prospect.id}/followups", json={"note": "sans date"}).status_code == 422


def test_history_lists_followups_and_events(client, add, clock):
    prospect = add("11111111100011", "SALON A")
    plan_followup(client, prospect.id, "2026-11-28", "Envoyer le devis")
    client.patch(f"/prospects/{prospect.id}/tracking", json={"status": "contacted"})

    history = client.get(f"/prospects/{prospect.id}/history").json()

    assert [f["note"] for f in history["followups"]] == ["Envoyer le devis"]
    assert history["followups"][0]["done_at"] is None
    assert [e["text"] for e in history["events"]][:2] == ["Statut : Contacté", "Relance prévue le 28/11/2026 : Envoyer le devis"]
    assert client.get("/prospects/999999/history").status_code == 404
