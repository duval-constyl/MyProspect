import csv
import io
from dataclasses import replace

from sqlalchemy import func, select

from app.collect import create_collection, run_collection
from app.db import get_session_factory
from app.models import Contact, Exclusion, Job, Prospect, ScoreRow, Tracking
from tests.test_collect import CIRCLE_ZONE, SALON, fake_osm, fake_registry

HEADER = [
    "siret", "nom", "naf", "ville_adresse", "telephone", "email", "site",
    "score_web", "priorite", "statut", "favori", "notes", "opposee_prospection",
]


def read_csv(response) -> list[list[str]]:
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "prospects.csv" in response.headers["content-disposition"]
    return list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))


def test_patch_tracking_updates_only_given_fields(client, add):
    prospect = add("11111111100011", "SALON A")

    first = client.patch(f"/prospects/{prospect.id}/tracking", json={"status": "contacted"})
    second = client.patch(f"/prospects/{prospect.id}/tracking", json={"notes": "Rappeler lundi"})
    third = client.patch(f"/prospects/{prospect.id}/tracking", json={"favorite": True})

    assert first.status_code == 200
    assert (first.json()["status"], first.json()["favorite"], first.json()["notes"]) == ("contacted", False, "")
    assert (second.json()["status"], second.json()["notes"]) == ("contacted", "Rappeler lundi")
    final = third.json()
    assert (final["status"], final["favorite"], final["notes"]) == ("contacted", True, "Rappeler lundi")
    assert final["updated_at"]


def test_invalid_status_422(client, add):
    prospect = add("11111111100011", "SALON A")

    response = client.patch(f"/prospects/{prospect.id}/tracking", json={"status": "vendu"})

    assert response.status_code == 422
    assert "status" in response.json()["detail"]
    assert "invalide" in response.json()["detail"]


def test_patch_tracking_unknown_prospect_404(client, db_session):
    response = client.patch("/prospects/999999/tracking", json={"favorite": True})

    assert response.status_code == 404
    assert response.json()["detail"] == "Prospect introuvable."


def test_delete_removes_prospect_contacts_scores_and_adds_exclusion(client, add, db_session):
    prospect_id = add("11111111100011", "SALON A", score=75, phone="0478000001", status="contacted").id

    response = client.delete(f"/prospects/{prospect_id}")

    assert response.status_code == 204
    db_session.expire_all()
    for model in (Prospect, Contact, ScoreRow, Tracking):
        assert db_session.scalar(select(func.count()).select_from(model)) == 0
    exclusion = db_session.get(Exclusion, "11111111100011")
    assert exclusion is not None and exclusion.reason == "deleted"
    assert client.get(f"/prospects/{prospect_id}").status_code == 404


async def test_do_not_contact_keeps_data_and_excludes_from_next_collect(client, add, db_session):
    prospect = add(SALON.siret, "SALON ECLAT", phone="0478000001")

    response = client.post(f"/prospects/{prospect.id}/do-not-contact")

    assert response.status_code == 200
    assert response.json()["status"] == "refused"
    db_session.expire_all()
    assert db_session.get(Exclusion, SALON.siret).reason == "do_not_contact"

    job = create_collection(db_session, "circle", CIRCLE_ZONE, ["96.02A"])
    renamed = replace(SALON, name="NOUVEAU NOM")
    await run_collection(job.id, get_session_factory(), registry=fake_registry(renamed), osm=fake_osm())

    db_session.expire_all()
    kept = db_session.get(Prospect, prospect.id)
    assert kept.name == "SALON ECLAT"  # kept, and not refreshed by the collection
    assert db_session.scalar(select(Tracking.status).where(Tracking.prospect_id == prospect.id)) == "refused"
    assert db_session.get(Job, job.id).total == 0


def test_csv_has_header_and_one_row_per_prospect(client, add):
    add("11111111100011", "SALON A", score=75, phone="0478000001", status="contacted", favorite=True)
    add("22222222200022", "SALON B", score=20, website="https://b.fr", opposed=True)

    rows = read_csv(client.get("/exports/prospects.csv", params={"sort": "name"}))

    assert rows[0] == HEADER
    assert len(rows) == 3
    first = dict(zip(HEADER, rows[1]))
    assert first["siret"] == "11111111100011"
    assert first["nom"] == "SALON A"
    assert first["ville_adresse"] == "12 RUE DE RIVOLI 75004 PARIS 04"
    assert first["telephone"] == "0478000001"
    assert first["score_web"] == "75"
    assert first["priorite"] == str(38 + 12 + 6)
    assert first["statut"] == "contacté"
    assert first["favori"] == "oui"
    assert first["opposee_prospection"] == "non"
    assert dict(zip(HEADER, rows[2]))["opposee_prospection"] == "oui"


def test_csv_empty_cells_for_missing_phone_email_site(client, add):
    add("11111111100011", "SALON NU")

    rows = read_csv(client.get("/exports/prospects.csv"))

    row = dict(zip(HEADER, rows[1]))
    assert (row["telephone"], row["email"], row["site"], row["score_web"]) == ("", "", "", "")
    assert row["statut"] == "nouveau"
    assert row["favori"] == "non"
    assert "None" not in rows[1] and "null" not in rows[1]


def test_csv_escapes_commas_quotes_and_newlines_in_notes(client, add, db_session):
    prospect = add("11111111100011", "SALON A")
    tricky = 'Gérant absent, rappeler "vers 14 h"\nPuis envoyer le devis'
    client.patch(f"/prospects/{prospect.id}/tracking", json={"notes": tricky})

    rows = read_csv(client.get("/exports/prospects.csv"))

    assert len(rows) == 2
    assert dict(zip(HEADER, rows[1]))["notes"] == tricky


def test_csv_neutralises_formulas_from_third_party_data(client, add):
    # OSM and registry values are third-party data: a spreadsheet must never run them,
    # and Excel reads « +33 4 78 … » as a (broken) formula.
    prospect = add("11111111100011", "=HYPERLINK(\"http://x\")", phone="+33 4 78 00 00 01")
    client.patch(f"/prospects/{prospect.id}/tracking", json={"notes": "@SUM(A1:A2)"})

    rows = read_csv(client.get("/exports/prospects.csv"))

    row = dict(zip(HEADER, rows[1]))
    assert row["nom"] == "'=HYPERLINK(\"http://x\")"
    assert row["telephone"] == "'+33 4 78 00 00 01"
    assert row["notes"] == "'@SUM(A1:A2)"
    assert row["siret"] == "11111111100011"


def test_csv_uses_the_list_filters(client, add):
    add("11111111100011", "SALON A", website="https://a.fr")
    add("22222222200022", "SALON B")

    rows = read_csv(client.get("/exports/prospects.csv", params={"has_site": "false"}))

    assert [row[1] for row in rows[1:]] == ["SALON B"]
