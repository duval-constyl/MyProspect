"""Reminders, the « Aujourd'hui » page and the follow-up history (V2 plan, Task 7).

Days are Paris calendar days (Europe/Paris), whatever the server's time zone.
"""

from datetime import UTC, date, datetime
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.history import french_date, record_event
from app.models import FollowUp, Prospect, TrackingEvent
from app.routers.prospects import OFFER_ORDER, ProspectFilters, _latest_contact, city_of, query_rows

router = APIRouter()

SessionDep = Annotated[Session, Depends(get_session)]
PARIS = ZoneInfo("Europe/Paris")
TOP_PRIORITY_SIZE = 20
# Already in a conversation, or not to be contacted: not « to contact first ».
NOT_TO_CONTACT_FIRST = {"contacted", "replied", "refused"}


def get_now() -> datetime:
    """Current instant; replaced in tests."""
    return datetime.now(UTC)


NowDep = Annotated[datetime, Depends(get_now)]


def paris_today(now: datetime) -> date:
    return now.astimezone(PARIS).date()


class FollowUpIn(BaseModel):
    due_on: date
    note: str = ""


class FollowUpOut(BaseModel):
    id: int
    prospect_id: int
    due_on: date
    note: str
    done_at: datetime | None


class FollowUpDue(BaseModel):
    id: int
    prospect_id: int
    prospect_name: str
    phone: str | None
    due_on: date
    note: str


class TopProspect(BaseModel):
    id: int
    name: str
    city: str | None
    phone: str | None
    best_offer: str
    score: int | None
    priority: int
    status: str


class Today(BaseModel):
    followups_due: list[FollowUpDue]
    top_priority: list[TopProspect]


class EventOut(BaseModel):
    at: datetime
    kind: str
    text: str


class History(BaseModel):
    followups: list[FollowUpOut]
    events: list[EventOut]


def _prospect_or_404(session: Session, prospect_id: int) -> Prospect:
    prospect = session.get(Prospect, prospect_id)
    if prospect is None:
        raise HTTPException(404, "Prospect introuvable.")
    return prospect


def _out(followup: FollowUp) -> FollowUpOut:
    return FollowUpOut.model_validate(followup, from_attributes=True)


def _summary(followup: FollowUp) -> str:
    return followup.note or "sans note"


@router.post("/prospects/{prospect_id}/followups", status_code=201)
def plan_followup(prospect_id: int, body: FollowUpIn, session: SessionDep) -> FollowUpOut:
    _prospect_or_404(session, prospect_id)
    followup = FollowUp(prospect_id=prospect_id, due_on=body.due_on, note=body.note.strip())
    session.add(followup)
    record_event(
        session, prospect_id, "followup", f"Relance prévue le {french_date(body.due_on)} : {_summary(followup)}"
    )
    session.commit()
    session.refresh(followup)
    return _out(followup)


@router.post("/followups/{followup_id}/done")
def complete_followup(followup_id: int, session: SessionDep, now: NowDep) -> FollowUpOut:
    followup = session.get(FollowUp, followup_id)
    if followup is None:
        raise HTTPException(404, "Relance introuvable.")
    if followup.done_at is None:
        followup.done_at = now
        record_event(session, followup.prospect_id, "followup", f"Relance faite : {_summary(followup)}")
        session.commit()
        session.refresh(followup)
    return _out(followup)


@router.get("/today")
def today(session: SessionDep, now: NowDep) -> Today:
    day = paris_today(now)
    due = session.execute(
        select(FollowUp, Prospect.name, _latest_contact("phone").label("phone"))
        .join(Prospect, Prospect.id == FollowUp.prospect_id)
        .where(FollowUp.done_at.is_(None), FollowUp.due_on <= day)
        .order_by(FollowUp.due_on, FollowUp.id)
    )
    followups_due = [
        FollowUpDue(
            id=row.FollowUp.id,
            prospect_id=row.FollowUp.prospect_id,
            prospect_name=row.name,
            phone=row.phone,
            due_on=row.FollowUp.due_on,
            note=row.FollowUp.note,
        )
        for row in due
    ]

    # Who to contact first: each prospect counts with its best offer.
    best: dict[int, tuple[int, int, str, object]] = {}
    for rank, offer in enumerate(OFFER_ORDER):
        for row in query_rows(session, ProspectFilters(offer=offer)):
            if row.status in NOT_TO_CONTACT_FIRST:
                continue
            current = best.get(row.prospect.id)
            if current is None or row.priority > current[0]:
                best[row.prospect.id] = (row.priority, rank, offer, row)
    ranked = sorted(best.values(), key=lambda item: (-item[0], item[1], item[3].prospect.name))
    top_priority = [
        TopProspect(
            id=row.prospect.id,
            name=row.prospect.name,
            city=city_of(row.prospect.address),
            phone=row.phone,
            best_offer=offer,
            score=row.score,
            priority=priority,
            status=row.status,
        )
        for priority, _, offer, row in ranked[:TOP_PRIORITY_SIZE]
    ]
    return Today(followups_due=followups_due, top_priority=top_priority)


@router.get("/prospects/{prospect_id}/history")
def history(prospect_id: int, session: SessionDep) -> History:
    _prospect_or_404(session, prospect_id)
    followups = session.scalars(
        select(FollowUp).where(FollowUp.prospect_id == prospect_id).order_by(FollowUp.due_on, FollowUp.id)
    )
    events = session.scalars(
        select(TrackingEvent)
        .where(TrackingEvent.prospect_id == prospect_id)
        .order_by(TrackingEvent.at.desc(), TrackingEvent.id.desc())
    )
    return History(
        followups=[_out(f) for f in followups],
        events=[EventOut(at=e.at, kind=e.kind, text=e.text) for e in events],
    )
