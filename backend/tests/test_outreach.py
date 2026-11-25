import json
from types import SimpleNamespace

import anthropic
import httpx
import pytest
from sqlalchemy import select

from app.domain import Offer
from app.models import Exclusion, OutreachDraft, ScoreRow
from app.outreach import (
    MODEL,
    ClaudeDrafter,
    DraftFacts,
    DraftRejected,
    DraftText,
    NothingToSay,
    generate_outreach,
)
from app.routers.outreach import get_drafter

NO_HTTPS = {"code": "no_https", "label": "Site sans HTTPS (connexion non sécurisée)", "points": 20}
NO_VIEWPORT = {"code": "no_viewport", "label": "Site non adapté au mobile (pas de balise viewport)", "points": 15}
SLOW = {"code": "slow_mobile", "label": "Site lent sur mobile (PageSpeed 30/100)", "points": 20}
SEO = {"code": "missing_seo_tags", "label": "Balises de référencement manquantes : titre, description, titre principal H1", "points": 15}


def set_reasons(session, prospect_id: int, offer: str, reasons: list[dict]) -> None:
    row = session.scalar(select(ScoreRow).where(ScoreRow.prospect_id == prospect_id, ScoreRow.offer == offer))
    value = sum(r["points"] for r in reasons)
    if row is None:
        session.add(ScoreRow(prospect_id=prospect_id, offer=offer, value=value, tier=1, reasons=reasons))
    else:
        row.reasons, row.value = reasons, value
    session.commit()


def fake_llm(subject="Votre site, Salon Éclat", body="Bonjour, votre site n'utilise pas HTTPS. Échangeons ?"):
    calls: list[DraftFacts] = []

    async def llm(facts: DraftFacts) -> DraftText:
        calls.append(facts)
        return DraftText(subject=subject if facts.channel == "email" else None, body=body)

    llm.calls = calls
    return llm


@pytest.fixture
def salon(add, db_session):
    prospect = add("11111111100011", "SALON ECLAT", score=20, address="12 RUE DE LA REPUBLIQUE 69001 LYON")
    set_reasons(db_session, prospect.id, "web", [NO_HTTPS])
    return prospect


@pytest.fixture(autouse=True)
def sender(monkeypatch):
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "sender_name", "Duval Exemple")
    monkeypatch.setattr(settings, "sender_business", "développeur web et mobile")
    monkeypatch.setattr(settings, "anthropic_api_key", None)


def words(text: str) -> int:
    return len(text.split())


async def test_email_draft_contains_source_sender_and_optout(salon, db_session):
    draft = await generate_outreach(salon.id, Offer.WEB, "email", db_session, llm=fake_llm())

    assert draft.source == "llm"
    assert draft.subject == "Votre site, Salon Éclat"
    assert "registre officiel des entreprises" in draft.body
    assert "Duval Exemple" in draft.body and "développeur web et mobile" in draft.body
    assert "STOP" in draft.body  # opt-out sentence


async def test_template_email_also_has_source_sender_and_optout(salon, db_session):
    draft = await generate_outreach(salon.id, Offer.WEB, "email", db_session, llm=None)

    assert draft.source == "template"
    assert draft.subject
    for expected in ("registre officiel des entreprises", "Duval Exemple", "STOP", "SALON ECLAT"):
        assert expected in draft.body


async def test_draft_mentions_only_given_reasons(salon, db_session):
    llm = fake_llm()

    llm_draft = await generate_outreach(salon.id, Offer.WEB, "email", db_session, llm=llm)
    template = await generate_outreach(salon.id, Offer.WEB, "email", db_session, llm=None)

    facts = llm.calls[0]
    assert facts.reasons == ["Site sans HTTPS (connexion non sécurisée)"]
    assert (facts.company, facts.trade, facts.city) == ("SALON ECLAT", "Coiffure", "LYON")
    assert (facts.sender_name, facts.sender_business) == ("Duval Exemple", "développeur web et mobile")
    for draft in (llm_draft, template):
        assert "HTTPS" in draft.body or "sécuris" in draft.body
        assert "lent" not in draft.body.lower() and "vitesse" not in draft.body.lower()


async def test_llm_mentioning_a_defect_not_in_the_reasons_is_rejected(salon, db_session):
    liar = fake_llm(body="Bonjour, votre site est lent sur mobile, je peux améliorer sa vitesse.")

    draft = await generate_outreach(salon.id, Offer.WEB, "email", db_session, llm=liar)

    assert draft.source == "template"


async def test_llm_promising_figures_is_rejected(salon, db_session):
    boaster = fake_llm(body="Bonjour, je vous garantis +30 % de clients grâce au HTTPS.")

    draft = await generate_outreach(salon.id, Offer.WEB, "email", db_session, llm=boaster)

    assert draft.source == "template"


async def test_call_script_under_120_words(add, db_session):
    prospect = add("11111111100011", "SALON AUX NOMBREUX DEFAUTS", score=70)
    set_reasons(db_session, prospect.id, "web", [NO_HTTPS, SEO, NO_VIEWPORT, SLOW])

    template = await generate_outreach(prospect.id, Offer.WEB, "call", db_session, llm=None)
    llm_draft = await generate_outreach(prospect.id, Offer.WEB, "call", db_session, llm=fake_llm(body="Bonjour " * 40))

    assert template.channel == "call" and template.subject is None
    assert words(template.body) <= 120
    assert "Duval Exemple" in template.body
    assert llm_draft.source == "llm" and words(llm_draft.body) <= 120


async def test_without_api_key_uses_template(salon, db_session):
    draft = await generate_outreach(salon.id, Offer.WEB, "email", db_session)

    assert draft.source == "template"
    assert draft.variant == "template:v1"


async def test_llm_error_falls_back_to_template(salon, db_session):
    async def broken(facts):
        raise anthropic.APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"))

    async def crashing(facts):
        raise RuntimeError("bug")

    for llm in (broken, crashing):
        draft = await generate_outreach(salon.id, Offer.WEB, "email", db_session, llm=llm)
        assert draft.source == "template"


async def test_overlong_llm_answer_is_rejected_then_template(salon, db_session):
    verbose = fake_llm(body="Votre site n'est pas en HTTPS. " * 40)

    draft = await generate_outreach(salon.id, Offer.WEB, "email", db_session, llm=verbose)

    assert draft.source == "template"


async def test_no_reason_for_the_offer_gives_nothing_to_say(salon, db_session):
    with pytest.raises(NothingToSay):
        await generate_outreach(salon.id, Offer.CLOUD, "email", db_session, llm=fake_llm())


async def test_variant_is_stored_for_later_statistics(salon, db_session):
    await generate_outreach(salon.id, Offer.WEB, "email", db_session, llm=fake_llm())
    await generate_outreach(salon.id, Offer.WEB, "call", db_session, llm=None)

    stored = db_session.scalars(select(OutreachDraft).order_by(OutreachDraft.id)).all()
    assert [(d.source, d.variant) for d in stored] == [
        ("llm", f"llm:{MODEL}:v1"),
        ("template", "template:v1"),
    ]
    assert all(d.offer == "web" and d.prospect_id == salon.id for d in stored)


# --- Claude drafter (Anthropic SDK client simulated) -------------------------


class FakeMessages:
    def __init__(self, response):
        self.response = response
        self.kwargs = None

    async def create(self, **kwargs):
        self.kwargs = kwargs
        return self.response


def response(text: str, stop_reason: str = "end_turn"):
    return SimpleNamespace(stop_reason=stop_reason, content=[SimpleNamespace(type="text", text=text)])


FACTS = DraftFacts(
    company="SALON ECLAT", trade="Coiffure", city="LYON", offer="web", channel="email",
    reasons=["Site sans HTTPS (connexion non sécurisée)"], sender_name="Duval Exemple",
    sender_business="développeur web et mobile",
)


async def test_claude_drafter_sends_only_the_facts_and_reads_structured_output():
    messages = FakeMessages(response(json.dumps({"subject": "Votre site", "body": "Bonjour."})))
    drafter = ClaudeDrafter(api_key="cle-test", client=SimpleNamespace(messages=messages))

    text = await drafter(FACTS)

    assert text == DraftText(subject="Votre site", body="Bonjour.")
    sent = messages.kwargs
    assert sent["model"] == MODEL == "claude-opus-5-5"
    assert sent["output_config"]["effort"] == "low"
    assert sent["output_config"]["format"]["type"] == "json_schema"
    prompt = sent["messages"][0]["content"]
    assert "SALON ECLAT" in prompt and "Site sans HTTPS" in prompt and "Duval Exemple" in prompt
    assert "vouvoie" in sent["system"] and "120 mots" in sent["system"]


async def test_claude_drafter_refusal_or_truncation_is_rejected():
    for stop_reason in ("refusal", "max_tokens"):
        messages = FakeMessages(response('{"subject": "x", "body": "y"}', stop_reason=stop_reason))
        drafter = ClaudeDrafter(api_key="cle-test", client=SimpleNamespace(messages=messages))
        with pytest.raises(DraftRejected):
            await drafter(FACTS)


# --- Routes -------------------------------------------------------------------


@pytest.fixture
def drafter_override(client):
    client.app.dependency_overrides[get_drafter] = lambda: fake_llm()
    yield
    client.app.dependency_overrides.pop(get_drafter, None)


def test_post_and_list_drafts(client, salon, drafter_override):
    created = client.post(f"/prospects/{salon.id}/outreach", json={"offer": "web", "channel": "email"})
    client.post(f"/prospects/{salon.id}/outreach", json={"offer": "web", "channel": "call"})

    assert created.status_code == 201
    body = created.json()
    assert (body["offer"], body["channel"], body["source"]) == ("web", "email", "llm")
    listed = client.get(f"/prospects/{salon.id}/outreach").json()
    assert [d["channel"] for d in listed] == ["call", "email"]  # newest first


def test_do_not_contact_prospect_returns_409(client, salon, db_session, drafter_override):
    db_session.add(Exclusion(siret=salon.siret, reason="do_not_contact"))
    db_session.commit()

    response = client.post(f"/prospects/{salon.id}/outreach", json={"offer": "web", "channel": "email"})

    assert response.status_code == 409
    assert "ne plus contacter" in response.json()["detail"]
    assert db_session.scalar(select(OutreachDraft.id)) is None


def test_unknown_prospect_404(client, db_session, drafter_override):
    response = client.post("/prospects/999999/outreach", json={"offer": "web", "channel": "email"})

    assert response.status_code == 404
    assert client.get("/prospects/999999/outreach").status_code == 404


def test_nothing_to_say_returns_422(client, salon, drafter_override):
    response = client.post(f"/prospects/{salon.id}/outreach", json={"offer": "cloud", "channel": "email"})

    assert response.status_code == 422
    assert "Aucun point" in response.json()["detail"]
