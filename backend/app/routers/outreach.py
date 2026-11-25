"""Outreach draft routes: prepare a draft, list a prospect's drafts. Nothing is ever sent."""

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_session
from app.models import OutreachDraft, Prospect
from app.outreach import (
    DoNotContact,
    Drafter,
    NothingToSay,
    ProspectNotFound,
    default_drafter,
    generate_outreach,
)

router = APIRouter()

SessionDep = Annotated[Session, Depends(get_session)]


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
