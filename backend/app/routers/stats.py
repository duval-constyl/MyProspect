"""Reply statistics of the outreach, per offer, variant or zone (V3 plan, Task 6).

A prospect counts as contacted once its status is contacted, replied or refused. The group
of a prospect is given by its latest draft (the one most likely sent); a contacted prospect
without draft goes under "none". By zone, every zone gets a row and a prospect counts in each
zone that contains it; contacted prospects outside every zone go under "none".
"""

from collections.abc import Iterable
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_session
from app.geo import point_in_zone
from app.models import OFFERS, OutreachDraft, Prospect, Tracking, Zone

router = APIRouter()

SessionDep = Annotated[Session, Depends(get_session)]
CONTACTED = ("contacted", "replied", "refused")
NONE_KEY = "none"


class OutreachStat(BaseModel):
    key: str
    contacted: int
    replied: int
    refused: int
    reply_rate: float


def _row(key: str, prospect_ids: Iterable[int], statuses: dict[int, str]) -> OutreachStat:
    counted = [statuses.get(pid) for pid in prospect_ids]
    contacted = sum(status in CONTACTED for status in counted)
    replied = counted.count("replied")
    return OutreachStat(
        key=key,
        contacted=contacted,
        replied=replied,
        refused=counted.count("refused"),
        reply_rate=replied / contacted if contacted else 0.0,
    )


@router.get("/stats/outreach")
def outreach_stats(
    session: SessionDep, group_by: Literal["offer", "variant", "zone"] = "offer"
) -> list[OutreachStat]:
    statuses = dict(session.execute(select(Tracking.prospect_id, Tracking.status)).all())
    latest: dict[int, tuple[str, str]] = {}
    for prospect_id, offer, variant in session.execute(
        select(OutreachDraft.prospect_id, OutreachDraft.offer, OutreachDraft.variant).order_by(
            OutreachDraft.created_at, OutreachDraft.id
        )
    ):
        latest[prospect_id] = (offer, variant)
    candidates = set(latest) | {pid for pid, status in statuses.items() if status in CONTACTED}

    if group_by == "zone":
        return _by_zone(session, candidates, statuses)

    index = 0 if group_by == "offer" else 1
    groups: dict[str, set[int]] = {}
    for prospect_id in candidates:
        key = latest[prospect_id][index] if prospect_id in latest else NONE_KEY
        groups.setdefault(key, set()).add(prospect_id)

    def order(key: str):
        if key == NONE_KEY:
            return (2, 0, key)
        if group_by == "offer" and key in OFFERS:
            return (0, OFFERS.index(key), key)
        return (1, 0, key)

    return [_row(key, groups[key], statuses) for key in sorted(groups, key=order)]


def _by_zone(session: Session, candidates: set[int], statuses: dict[int, str]) -> list[OutreachStat]:
    positions = {
        pid: (lat, long)
        for pid, lat, long in session.execute(
            select(Prospect.id, func.ST_Y(Prospect.geom), func.ST_X(Prospect.geom)).where(
                Prospect.id.in_(candidates), Prospect.geom.is_not(None)
            )
        )
    }
    zones = session.scalars(select(Zone).order_by(Zone.collected_at.desc(), Zone.id.desc())).all()
    rows, inside_any = [], set()
    for zone in zones:
        inside = {
            pid for pid, (lat, long) in positions.items() if point_in_zone(zone.kind, zone.geojson, lat, long)
        }
        inside_any |= inside
        rows.append(_row(str(zone.id), inside, statuses))
    outside = {pid for pid in candidates - inside_any if statuses.get(pid) in CONTACTED}
    if outside:
        rows.append(_row(NONE_KEY, outside, statuses))
    return rows
