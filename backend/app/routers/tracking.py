"""Follow-up of a prospect: status, favourite, notes; deletion and do-not-contact list."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db import get_session
from app.domain import Status
from app.history import STATUS_LABELS, record_event
from app.models import Exclusion, Prospect, Tracking
from app.schemas import TrackingOut

router = APIRouter()

SessionDep = Annotated[Session, Depends(get_session)]


class TrackingPatch(BaseModel):
    status: Status | None = None
    favorite: bool | None = None
    notes: str | None = None


def _prospect_or_404(session: Session, prospect_id: int) -> Prospect:
    prospect = session.get(Prospect, prospect_id)
    if prospect is None:
        raise HTTPException(404, "Prospect introuvable.")
    return prospect


def _tracking_of(session: Session, prospect_id: int) -> Tracking:
    tracking = session.query(Tracking).filter_by(prospect_id=prospect_id).one_or_none()
    if tracking is None:
        tracking = Tracking(prospect_id=prospect_id, status=Status.NEW.value, favorite=False, notes="")
        session.add(tracking)
    return tracking


def _out(tracking: Tracking) -> TrackingOut:
    return TrackingOut(
        status=tracking.status,
        favorite=tracking.favorite,
        notes=tracking.notes,
        updated_at=tracking.updated_at,
    )


def _exclude(session: Session, siret: str, reason: str) -> None:
    statement = insert(Exclusion).values(siret=siret, reason=reason)
    session.execute(
        statement.on_conflict_do_update(index_elements=[Exclusion.siret], set_={"reason": reason})
    )


@router.patch("/prospects/{prospect_id}/tracking")
def update_tracking(prospect_id: int, body: TrackingPatch, session: SessionDep) -> TrackingOut:
    _prospect_or_404(session, prospect_id)
    tracking = _tracking_of(session, prospect_id)
    changes = {key: value for key, value in body.model_dump(exclude_unset=True).items() if value is not None}
    for key, value in changes.items():
        value = value.value if isinstance(value, Status) else value
        if key == "status" and value != tracking.status:
            record_event(session, prospect_id, "status", f"Statut : {STATUS_LABELS[value]}")
        if key == "notes" and value != tracking.notes:
            record_event(session, prospect_id, "note", value or "Notes effacées")
        setattr(tracking, key, value)
    session.commit()
    session.refresh(tracking)
    return _out(tracking)


@router.delete("/prospects/{prospect_id}", status_code=204)
def delete_prospect(prospect_id: int, session: SessionDep) -> Response:
    """Permanent deletion of the prospect's data; its SIRET is never collected again."""
    prospect = _prospect_or_404(session, prospect_id)
    _exclude(session, prospect.siret, "deleted")
    # Contacts, analysis, scores and tracking go with it (ON DELETE CASCADE).
    session.execute(delete(Prospect).where(Prospect.id == prospect_id))
    session.commit()
    return Response(status_code=204)


@router.post("/prospects/{prospect_id}/do-not-contact")
def do_not_contact(prospect_id: int, session: SessionDep) -> TrackingOut:
    """Status « refused » and do-not-contact list; the data is kept."""
    prospect = _prospect_or_404(session, prospect_id)
    tracking = _tracking_of(session, prospect_id)
    tracking.status = Status.REFUSED.value
    record_event(session, prospect_id, "status", f"Statut : {STATUS_LABELS['refused']} (ne plus contacter)")
    _exclude(session, prospect.siret, "do_not_contact")
    session.commit()
    session.refresh(tracking)
    return _out(tracking)
