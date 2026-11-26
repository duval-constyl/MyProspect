"""Alerts of the watched zones: new companies and companies found closed (V3 Task 5)."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Alert, Prospect, Zone
from app.watch import zone_label

router = APIRouter()

SessionDep = Annotated[Session, Depends(get_session)]


class AlertOut(BaseModel):
    id: int
    kind: str
    zone_id: int
    zone_label: str
    prospect_id: int
    prospect_name: str
    created_at: datetime
    seen_at: datetime | None


def _out(alert: Alert, prospect_name: str, zone: Zone) -> AlertOut:
    return AlertOut(
        id=alert.id,
        kind=alert.kind,
        zone_id=alert.zone_id,
        zone_label=zone_label(zone),
        prospect_id=alert.prospect_id,
        prospect_name=prospect_name,
        created_at=alert.created_at,
        seen_at=alert.seen_at,
    )


@router.get("/alerts")
def list_alerts(session: SessionDep, unseen: bool = False) -> list[AlertOut]:
    query = (
        select(Alert, Prospect.name, Zone)
        .join(Prospect, Prospect.id == Alert.prospect_id)
        .join(Zone, Zone.id == Alert.zone_id)
        .order_by(Alert.created_at.desc(), Alert.id.desc())
    )
    if unseen:
        query = query.where(Alert.seen_at.is_(None))
    return [_out(alert, name, zone) for alert, name, zone in session.execute(query)]


@router.post("/alerts/{alert_id}/seen")
def mark_seen(alert_id: int, session: SessionDep) -> AlertOut:
    alert = session.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(404, "Alerte introuvable.")
    if alert.seen_at is None:
        alert.seen_at = datetime.now(UTC)
        session.commit()
    prospect = session.get(Prospect, alert.prospect_id)
    return _out(alert, prospect.name, session.get(Zone, alert.zone_id))
