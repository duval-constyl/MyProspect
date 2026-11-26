from datetime import UTC, datetime

import pytest

from app.domain import Offer
from app.models import SiteAnalysisRow, Tracking
from app.report import render_audit_html, render_audit_pdf
from app.routers.prospects import prospect_detail
from tests.test_outreach import NO_HTTPS, NO_VIEWPORT, set_reasons

SECRET_NOTE = "Note privée : le gérant est difficile, insister lundi"


@pytest.fixture(autouse=True)
def sender(monkeypatch):
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "sender_name", "Duval Exemple")
    monkeypatch.setattr(settings, "sender_business", "développeur web et mobile")


@pytest.fixture
def salon(add, db_session):
    prospect = add(
        "11111111100011", "SALON ECLAT", score=35, phone="0478000001", website="https://salon-eclat.fr",
        status="contacted", favorite=True, address="12 RUE DE LA REPUBLIQUE 69001 LYON",
    )
    set_reasons(db_session, prospect.id, "web", [NO_HTTPS, NO_VIEWPORT])
    db_session.add(
        SiteAnalysisRow(
            prospect_id=prospect.id, url="https://salon-eclat.fr/", reachable=True, https=False,
            has_title=True, has_description=False, has_h1=True, has_viewport=False,
            response_ms=1840, tech=["wordpress@5.8"], mobile_perf=None,
            analyzed_at=datetime(2026, 11, 25, tzinfo=UTC),
        )
    )
    tracking = db_session.query(Tracking).filter_by(prospect_id=prospect.id).one()
    tracking.notes = SECRET_NOTE
    db_session.commit()
    return prospect


def detail_of(session, prospect_id):
    return prospect_detail(prospect_id, session)


def test_html_contains_score_and_every_reason(salon, db_session):
    html = render_audit_html(detail_of(db_session, salon.id), Offer.WEB)

    assert "SALON ECLAT" in html
    assert "35" in html and "Palier 3 / 6" in html
    assert "HTTPS" in html
    assert "mobile" in html
    assert "1,8 s" in html  # response time in plain language
    assert "Duval Exemple" in html and "développeur web et mobile" in html


def test_html_never_contains_private_notes_or_status(salon, add, db_session):
    add("22222222200022", "AUTRE PROSPECT CONFIDENTIEL", score=75)
    detail = detail_of(db_session, salon.id)

    html = render_audit_html(detail, Offer.WEB)

    assert SECRET_NOTE not in html and "difficile" not in html
    assert "Contacté" not in html and "contacted" not in html
    assert "Favori" not in html and "favori" not in html
    assert "Priorité" not in html and "priorité" not in html
    assert "AUTRE PROSPECT CONFIDENTIEL" not in html
    assert "0478000001" not in html  # the prospect's own contact details are not needed either


def test_prospect_without_site_renders(add, db_session):
    prospect = add("33333333300033", "PLOMBERIE SANS SITE", score=75)

    html = render_audit_html(detail_of(db_session, prospect.id), Offer.WEB)

    assert "PLOMBERIE SANS SITE" in html
    assert "Aucun site web connu" in html
    assert "Temps de réponse" not in html


def test_long_company_name_renders(add, db_session):
    long_name = "SOCIETE DES ETABLISSEMENTS " * 8 + "<script>alert(1)</script>"  # 241 characters
    prospect = add("44444444400044", long_name.strip(), score=75)

    html = render_audit_html(detail_of(db_session, prospect.id), Offer.WEB)
    pdf = render_audit_pdf(detail_of(db_session, prospect.id), Offer.WEB)

    assert "SOCIETE DES ETABLISSEMENTS" in html
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert pdf.startswith(b"%PDF-")


def test_pdf_starts_with_pdf_header_and_is_not_empty(salon, db_session):
    pdf = render_audit_pdf(detail_of(db_session, salon.id), Offer.WEB)

    assert pdf.startswith(b"%PDF-")
    assert len(pdf) > 2000


def test_offer_without_reasons_says_so(salon, db_session):
    html = render_audit_html(detail_of(db_session, salon.id), Offer.CLOUD)

    assert "Aucun point d'amélioration relevé" in html


def test_route_returns_a_pdf_download(client, salon):
    response = client.get(f"/prospects/{salon.id}/audit.pdf", params={"offer": "web"})

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert "audit-11111111100011-web.pdf" in response.headers["content-disposition"]
    assert response.content.startswith(b"%PDF-")


def test_unknown_prospect_404(client, db_session):
    response = client.get("/prospects/999999/audit.pdf")

    assert response.status_code == 404
    assert response.json()["detail"] == "Prospect introuvable."


def test_report_can_be_disabled(client, salon, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "audit_report_enabled", False)

    response = client.get(f"/prospects/{salon.id}/audit.pdf")

    assert response.status_code == 404
    assert "désactivé" in response.json()["detail"]
