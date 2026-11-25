"""Follow-up history: one event per status change, note change or reminder (V2 Task 7)."""

from datetime import date

from sqlalchemy.orm import Session

from app.models import TrackingEvent

STATUS_LABELS = {
    "new": "Nouveau",
    "to_contact": "À contacter",
    "contacted": "Contacté",
    "replied": "A répondu",
    "refused": "Refusé",
}


def record_event(session: Session, prospect_id: int, kind: str, text: str) -> None:
    session.add(TrackingEvent(prospect_id=prospect_id, kind=kind, text=text))


def french_date(day: date) -> str:
    return day.strftime("%d/%m/%Y")
