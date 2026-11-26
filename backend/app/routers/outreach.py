"""Outreach draft routes: prepare a draft, list a prospect's drafts, download one as .eml.

Nothing is ever sent: the .eml file opens as a draft in the mail client.
"""

import re
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_session
from app.eml import build_eml
from app.models import Exclusion, OutreachDraft, Prospect
from app.outreach import (
    DoNotContact,
    Drafter,
    NothingToSay,
    ProspectNotFound,
    default_drafter,
    generate_outreach,
)
from app.routers.exports import audit_pdf_for
from app.routers.prospects import prospect_detail

router = APIRouter()

SessionDep = Annotated[Session, Depends(get_session)]
# One address, no spaces or line breaks (nothing can be slipped into the other headers).
EMAIL_ADDRESS = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


def get_drafter() -> Drafter | None:
    """The language model writer; replaced in tests so that nothing hits the network."""
    return default_drafter(get_settings().anthropic_api_key)


class OutreachRequest(BaseModel):
    offer: Literal["web", "mobile", "cloud"]
    channel: Literal["email", "call"]


class DraftOut(BaseModel):
    id: int
    offer: str
    channel: str
    subject: str | None
    body: str
    source: str
    variant: str
    created_at: datetime


def _out(draft: OutreachDraft) -> DraftOut:
    return DraftOut.model_validate(draft, from_attributes=True)


@router.post("/prospects/{prospect_id}/outreach", status_code=201)
async def prepare_draft(
    prospect_id: int,
    body: OutreachRequest,
    session: SessionDep,
    drafter: Annotated[Drafter | None, Depends(get_drafter)],
) -> DraftOut:
    try:
        draft = await generate_outreach(prospect_id, body.offer, body.channel, session, llm=drafter)
    except ProspectNotFound as exc:
        raise HTTPException(404, str(exc)) from None
    except DoNotContact as exc:
        raise HTTPException(409, str(exc)) from None
    except NothingToSay as exc:
        raise HTTPException(422, str(exc)) from None
    return _out(draft)


@router.get("/prospects/{prospect_id}/outreach")
def list_drafts(prospect_id: int, session: SessionDep) -> list[DraftOut]:
    if session.get(Prospect, prospect_id) is None:
        raise HTTPException(404, "Prospect introuvable.")
    drafts = session.scalars(
        select(OutreachDraft)
        .where(OutreachDraft.prospect_id == prospect_id)
        .order_by(OutreachDraft.created_at.desc(), OutreachDraft.id.desc())
    )
    return [_out(draft) for draft in drafts]


@router.get("/outreach/{draft_id}/draft.eml")
async def draft_eml(draft_id: int, session: SessionDep, to: str | None = None, audit: bool = False) -> Response:
    """The e-mail draft as an unsent .eml file, the audit report attached on request."""
    draft = session.get(OutreachDraft, draft_id)
    if draft is None:
        raise HTTPException(404, "Brouillon introuvable.")
    if draft.channel != "email":
        raise HTTPException(409, "Un script d'appel n'a pas de fichier e-mail.")
    prospect = session.get(Prospect, draft.prospect_id)
    if session.scalar(
        select(Exclusion.siret).where(Exclusion.siret == prospect.siret, Exclusion.reason == "do_not_contact")
    ):
        raise HTTPException(409, "Ce prospect est sur la liste « ne plus contacter » : aucun e-mail.")
    to = (to or "").strip()
    if not to:
        raise HTTPException(422, "Indiquez l'adresse e-mail du destinataire.")
    if not EMAIL_ADDRESS.fullmatch(to):
        raise HTTPException(422, "Adresse e-mail du destinataire invalide.")

    settings = get_settings()
    audit_pdf = None
    if audit:
        if not settings.audit_report_enabled:
            raise HTTPException(404, "Rapport d'audit désactivé dans les réglages.")
        audit_pdf = await audit_pdf_for(prospect_detail(draft.prospect_id, session), draft.offer)
    content = build_eml(draft, to, settings.sender_name, settings.sender_email, audit_pdf=audit_pdf)
    return Response(
        content=content,
        media_type="message/rfc822",
        headers={"Content-Disposition": f'attachment; filename="brouillon-{draft.id}.eml"'},
    )
