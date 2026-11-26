import ast
import email
from email import policy
from pathlib import Path

import pytest

import app.eml
import app.routers.outreach as outreach_router
from app.eml import build_eml
from app.models import OutreachDraft

BODY = "Bonjour,\n\nVotre site n'est pas lisible sur téléphone.\nJe peux vous montrer comment l'améliorer.\n\nCordialement,\nJean Dupont"
TO = "contact@salon-eclat.fr"


def email_draft(subject: str = "Votre site sur téléphone", body: str = BODY) -> OutreachDraft:
    return OutreachDraft(
        offer="web", channel="email", subject=subject, body=body, source="template", variant="template:v1"
    )


def parse(raw: bytes):
    return email.message_from_bytes(raw, policy=policy.default)


def saved_draft(session, add, channel: str = "email") -> OutreachDraft:
    prospect = add("11111111100011", "SALON ECLAT", email=TO)
    draft = OutreachDraft(
        prospect_id=prospect.id,
        offer="web",
        channel=channel,
        subject="Votre site sur téléphone" if channel == "email" else None,
        body=BODY,
        source="template",
        variant="template:v1",
    )
    session.add(draft)
    session.commit()
    return draft


def test_eml_has_headers_and_unsent_flag():
    raw = build_eml(email_draft(), TO, "Jean Dupont", "jean@exemple.fr")

    message = parse(raw)
    assert message["To"] == TO
    assert message["From"] == "Jean Dupont <jean@exemple.fr>"
    assert message["Subject"] == "Votre site sur téléphone"
    assert message["X-Unsent"] == "1"
    assert b"\r\n" in raw  # standard .eml line endings


def test_without_sender_email_the_mail_client_chooses_the_sender():
    message = parse(build_eml(email_draft(), TO, "Jean Dupont", ""))

    assert message["From"] is None
    assert message["X-Unsent"] == "1"


def test_accents_and_long_subject_are_encoded_correctly():
    phrase = "Une idée pour être trouvé et réservé en ligne, sans effort de votre côté, à Villeurbanne "
    subject = (phrase * 2)[:120]
    assert len(subject) == 120 and "é" in subject

    raw = build_eml(email_draft(subject=subject), TO, "Jérôme Dupré", "jerome@exemple.fr")

    headers = raw.split(b"\r\n\r\n", 1)[0]
    headers.decode("ascii")  # encoded words only: no raw accent in the headers
    assert all(len(line) <= 78 for line in headers.split(b"\r\n"))
    message = parse(raw)
    assert message["Subject"] == subject
    assert message["From"].addresses[0].display_name == "Jérôme Dupré"
    assert "téléphone" in message.get_body(preferencelist=("plain",)).get_content()


def test_body_line_breaks_preserved():
    message = parse(build_eml(email_draft(), TO, "Jean Dupont", "jean@exemple.fr"))

    content = message.get_body(preferencelist=("plain",)).get_content()
    assert content.splitlines() == BODY.splitlines()


def test_pdf_attached_when_given():
    raw = build_eml(email_draft(), TO, "Jean Dupont", "jean@exemple.fr", audit_pdf=b"%PDF-1.7 rapport")

    message = parse(raw)
    attachments = list(message.iter_attachments())
    assert len(attachments) == 1
    assert attachments[0].get_content_type() == "application/pdf"
    assert attachments[0].get_filename() == "rapport-audit.pdf"
    assert attachments[0].get_content() == b"%PDF-1.7 rapport"
    assert message.get_body(preferencelist=("plain",)).get_content().splitlines() == BODY.splitlines()


def test_eml_route_downloads_a_draft_file(client, db_session, add):
    draft = saved_draft(db_session, add)

    response = client.get(f"/outreach/{draft.id}/draft.eml", params={"to": TO})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("message/rfc822")
    assert response.headers["content-disposition"] == f'attachment; filename="brouillon-{draft.id}.eml"'
    message = parse(response.content)
    assert message["To"] == TO
    assert message["X-Unsent"] == "1"
    assert list(message.iter_attachments()) == []


def test_eml_route_attaches_audit_report_when_asked(client, db_session, add, monkeypatch):
    draft = saved_draft(db_session, add)
    calls = []

    async def fake_audit_pdf(detail, offer):
        calls.append((detail.id, offer))
        return b"%PDF-1.7 rapport"

    monkeypatch.setattr(outreach_router, "audit_pdf_for", fake_audit_pdf)

    response = client.get(f"/outreach/{draft.id}/draft.eml", params={"to": TO, "audit": "true"})

    assert response.status_code == 200
    assert calls == [(draft.prospect_id, "web")]
    [attachment] = list(parse(response.content).iter_attachments())
    assert attachment.get_content() == b"%PDF-1.7 rapport"


@pytest.mark.parametrize("params", [{}, {"to": "  "}, {"to": "pas-une-adresse"}, {"to": f"{TO}\r\nBcc: autre@exemple.fr"}])
def test_missing_to_returns_422(client, db_session, add, params):
    draft = saved_draft(db_session, add)

    response = client.get(f"/outreach/{draft.id}/draft.eml", params=params)

    assert response.status_code == 422
    assert response.json()["detail"] in (
        "Indiquez l'adresse e-mail du destinataire.",
        "Adresse e-mail du destinataire invalide.",
    )


def test_call_draft_returns_409(client, db_session, add):
    draft = saved_draft(db_session, add, channel="call")

    response = client.get(f"/outreach/{draft.id}/draft.eml", params={"to": TO})

    assert response.status_code == 409
    assert response.json()["detail"] == "Un script d'appel n'a pas de fichier e-mail."


def test_unknown_draft_returns_404(client):
    response = client.get("/outreach/999999/draft.eml", params={"to": TO})

    assert response.status_code == 404
    assert response.json()["detail"] == "Brouillon introuvable."


def test_module_does_not_import_smtplib():
    for module in (app.eml, outreach_router):
        tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
        imported = {alias.name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
        imported |= {node.module.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
        assert "smtplib" not in imported, module.__name__


def test_do_not_contact_prospect_returns_409(client, db_session, add):
    draft = saved_draft(db_session, add)
    assert client.post(f"/prospects/{draft.prospect_id}/do-not-contact").status_code == 200

    response = client.get(f"/outreach/{draft.id}/draft.eml", params={"to": TO})

    assert response.status_code == 409
    assert "ne plus contacter" in response.json()["detail"]
