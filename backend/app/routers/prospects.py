"""Prospects API: filtered list, map clusters, counters, detail (V1 plan, Task 10).

The contact priority is computed when reading, with `contact_priority` and the
home position from the settings, so changing the rules never needs a migration.
"""

import dataclasses
import re
from dataclasses import dataclass
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Select, and_, exists, func, or_, select
from sqlalchemy.orm import Session, aliased

from app.config import get_settings
from app.db import get_session
from app.domain import Offer, Status
from app.geo import distance_m
from app.models import Contact, Prospect, ScoreRow, SiteAnalysisRow, Tracking
from app.schemas import (
    Cluster,
    Clusters,
    ContactOut,
    PriorityOut,
    ProspectDetail,
    ProspectList,
    ProspectListItem,
    ReasonOut,
    ScoreOut,
    SiteAnalysisOut,
    Stats,
    TrackingOut,
)
from app.scoring.priority import contact_priority
from app.scoring.web import tier_of

router = APIRouter()

SessionDep = Annotated[Session, Depends(get_session)]
CITY = re.compile(r"\b\d{5}\s+(.+)$")
CLUSTER_CELLS_PER_TILE = 4  # about 64 px per cluster cell on 256 px tiles
OFFER_ORDER = [Offer.WEB.value, Offer.MOBILE.value, Offer.CLOUD.value]


@dataclass(frozen=True)
class ProspectFilters:
    bbox: tuple[float, float, float, float] | None = None
    naf: list[str] | None = None
    has_site: bool | None = None
    offer: str = Offer.WEB.value
    score_min: int | None = None
    status: str | None = None
    q: str | None = None
    favorite: bool | None = None
    opposed: bool | None = None
    sort: str = "priority"
    order: str | None = None


def parse_bbox(bbox: str | None) -> tuple[float, float, float, float] | None:
    if not bbox:
        return None
    try:
        west, south, east, north = (float(part) for part in bbox.split(","))
    except ValueError:
        raise HTTPException(422, "bbox invalide : attendu ouest,sud,est,nord.") from None
    return west, south, east, north


def prospect_filters(
    bbox: str | None = None,
    naf: str | None = None,
    has_site: bool | None = None,
    offer: Literal["web", "mobile", "cloud"] = "web",
    score_min: Annotated[int | None, Query(ge=0, le=100)] = None,
    status: Literal["new", "to_contact", "contacted", "replied", "refused"] | None = None,
    q: str | None = None,
    favorite: bool | None = None,
    opposed: bool | None = None,
    sort: Literal["priority", "score", "name"] = "priority",
    order: Literal["asc", "desc"] | None = None,
) -> ProspectFilters:
    """Query parameters shared by the list and the CSV export."""
    codes = [code.strip() for code in naf.split(",") if code.strip()] if naf else None
    return ProspectFilters(
        bbox=parse_bbox(bbox),
        naf=codes or None,
        has_site=has_site,
        offer=offer,
        score_min=score_min,
        status=status,
        q=(q or "").strip() or None,
        favorite=favorite,
        opposed=opposed,
        sort=sort,
        order=order,
    )


FiltersDep = Annotated[ProspectFilters, Depends(prospect_filters)]


@dataclass(frozen=True)
class ProspectRow:
    """One prospect of the list, with what the list and the export show."""

    prospect: Prospect
    lat: float | None
    long: float | None
    score: int | None  # score of the selected offer
    tier: int | None
    score_web: int | None
    phone: str | None
    email: str | None
    website: str | None
    status: str
    favorite: bool
    notes: str
    priority: int


def _latest_contact(kind: str):
    return (
        select(Contact.value)
        .where(Contact.prospect_id == Prospect.id, Contact.kind == kind)
        .order_by(Contact.seen_on.desc(), Contact.id.desc())
        .limit(1)
        .correlate(Prospect)
        .scalar_subquery()
    )


def _envelope(bbox: tuple[float, float, float, float]):
    return func.ST_MakeEnvelope(*bbox, 4326)


def _has_site():
    return exists().where(Contact.prospect_id == Prospect.id, Contact.kind == "website")


def _rows_query(filters: ProspectFilters) -> Select:
    score = aliased(ScoreRow)
    web = aliased(ScoreRow)
    status = func.coalesce(Tracking.status, Status.NEW.value)
    favorite = func.coalesce(Tracking.favorite, False)
    query = (
        select(
            Prospect,
            func.ST_Y(Prospect.geom).label("lat"),
            func.ST_X(Prospect.geom).label("long"),
            score.value.label("score"),
            score.tier.label("tier"),
            web.value.label("score_web"),
            _latest_contact("phone").label("phone"),
            _latest_contact("email").label("email"),
            _latest_contact("website").label("website"),
            status.label("status"),
            favorite.label("favorite"),
            func.coalesce(Tracking.notes, "").label("notes"),
        )
        .outerjoin(score, and_(score.prospect_id == Prospect.id, score.offer == filters.offer))
        .outerjoin(web, and_(web.prospect_id == Prospect.id, web.offer == Offer.WEB.value))
        .outerjoin(Tracking, Tracking.prospect_id == Prospect.id)
    )
    if filters.bbox:
        query = query.where(func.ST_Intersects(Prospect.geom, _envelope(filters.bbox)))
    if filters.naf:
        query = query.where(Prospect.naf.in_(filters.naf))
    if filters.has_site is not None:
        query = query.where(_has_site() if filters.has_site else ~_has_site())
    if filters.score_min is not None:
        query = query.where(score.value >= filters.score_min)
    if filters.status:
        query = query.where(status == filters.status)
    if filters.favorite is not None:
        query = query.where(favorite == filters.favorite)
    if filters.opposed is not None:
        query = query.where(Prospect.opposed_to_prospecting == filters.opposed)
    if filters.q:
        digits = filters.q.replace(" ", "")
        name_match = Prospect.name.ilike(f"%{filters.q}%")
        query = query.where(
            or_(name_match, Prospect.siret.like(f"{digits}%")) if digits.isdigit() else name_match
        )
    return query


def _priority(prospect: Prospect, lat, long, score, phone, email) -> tuple[int, list]:
    settings = get_settings()
    distance_km = (
        distance_m(settings.home_lat, settings.home_long, lat, long) / 1000
        if lat is not None and long is not None
        else None
    )
    return contact_priority(
        score or 0, phone is not None, email is not None, prospect.effectif_code, distance_km
    )


def query_rows(session: Session, filters: ProspectFilters) -> list[ProspectRow]:
    """Filtered and sorted rows (the priority is computed here, then used to sort)."""
    rows = []
    for record in session.execute(_rows_query(filters)):
        priority, _ = _priority(
            record.Prospect, record.lat, record.long, record.score, record.phone, record.email
        )
        rows.append(
            ProspectRow(
                prospect=record.Prospect,
                lat=record.lat,
                long=record.long,
                score=record.score,
                tier=record.tier,
                score_web=record.score_web,
                phone=record.phone,
                email=record.email,
                website=record.website,
                status=record.status,
                favorite=record.favorite,
                notes=record.notes,
                priority=priority,
            )
        )
    descending = (filters.order or ("asc" if filters.sort == "name" else "desc")) == "desc"
    if filters.sort == "name":
        key = lambda row: (row.prospect.name.lower(), row.prospect.siret)  # noqa: E731
    elif filters.sort == "score":
        key = lambda row: (row.score if row.score is not None else -1, row.prospect.name.lower())  # noqa: E731
    else:
        key = lambda row: (row.priority, row.score or 0)  # noqa: E731
    rows.sort(key=key, reverse=descending)
    return rows


def city_of(address: str) -> str | None:
    match = CITY.search(address or "")
    return match.group(1).strip() if match else None


@router.get("/prospects")
def list_prospects(
    session: SessionDep,
    filters: FiltersDep,
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=500)] = 50,
) -> ProspectList:
    rows = query_rows(session, filters)
    start = (page - 1) * per_page
    items = [
        ProspectListItem(
            id=row.prospect.id,
            siret=row.prospect.siret,
            name=row.prospect.name,
            naf=row.prospect.naf,
            address=row.prospect.address,
            city=city_of(row.prospect.address),
            lat=row.lat,
            long=row.long,
            score=row.score,
            score_web=row.score_web,
            tier=row.tier,
            priority=row.priority,
            status=row.status,
            favorite=row.favorite,
            has_site=row.website is not None,
            phone=row.phone,
            email=row.email,
            website=row.website,
            opposed_to_prospecting=row.prospect.opposed_to_prospecting,
        )
        for row in rows[start : start + per_page]
    ]
    return ProspectList(items=items, total=len(rows))


@router.get("/prospects/clusters")
def prospect_clusters(
    session: SessionDep,
    bbox: str,
    zoom: Annotated[int, Query(ge=0, le=22)],
    offer: Literal["web", "mobile", "cloud"] = "web",
) -> Clusters:
    envelope = _envelope(parse_bbox(bbox))
    cell = 360 / (2**zoom) / CLUSTER_CELLS_PER_TILE
    score = aliased(ScoreRow)
    centre = func.ST_Centroid(func.ST_Collect(Prospect.geom))
    query = (
        select(
            func.ST_Y(centre).label("lat"),
            func.ST_X(centre).label("long"),
            func.count().label("count"),
            func.max(score.value).label("max_score"),
            func.min(Prospect.id).label("first_id"),
        )
        .outerjoin(score, and_(score.prospect_id == Prospect.id, score.offer == offer))
        .where(Prospect.geom.is_not(None), func.ST_Intersects(Prospect.geom, envelope))
        .group_by(func.ST_SnapToGrid(Prospect.geom, cell))
    )
    return Clusters(
        clusters=[
            Cluster(
                lat=row.lat,
                long=row.long,
                count=row.count,
                max_score=row.max_score,
                tier=tier_of(row.max_score) if row.max_score is not None else None,
                prospect_id=row.first_id if row.count == 1 else None,
            )
            for row in session.execute(query)
        ]
    )


@router.get("/prospects/stats")
def prospect_stats(session: SessionDep, bbox: str | None = None) -> Stats:
    query = select(
        func.count().label("in_view"),
        func.count().filter(_has_site()).label("with_site"),
    ).select_from(Prospect)
    if bbox:
        query = query.where(func.ST_Intersects(Prospect.geom, _envelope(parse_bbox(bbox))))
    row = session.execute(query).one()
    return Stats(in_view=row.in_view, with_site=row.with_site, without_site=row.in_view - row.with_site)


@router.get("/prospects/{prospect_id}")
def prospect_detail(prospect_id: int, session: SessionDep) -> ProspectDetail:
    record = session.execute(
        select(Prospect, func.ST_Y(Prospect.geom).label("lat"), func.ST_X(Prospect.geom).label("long"))
        .where(Prospect.id == prospect_id)
    ).one_or_none()
    if record is None:
        raise HTTPException(404, "Prospect introuvable.")
    prospect, lat, long = record.Prospect, record.lat, record.long

    contacts = list(
        session.scalars(
            select(Contact)
            .where(Contact.prospect_id == prospect.id)
            .order_by(Contact.kind, Contact.seen_on.desc(), Contact.id.desc())
        )
    )
    analysis = session.scalar(select(SiteAnalysisRow).where(SiteAnalysisRow.prospect_id == prospect.id))
    scores = list(
        session.scalars(select(ScoreRow).where(ScoreRow.prospect_id == prospect.id))
    )
    scores.sort(key=lambda s: OFFER_ORDER.index(s.offer) if s.offer in OFFER_ORDER else len(OFFER_ORDER))
    tracking = session.scalar(select(Tracking).where(Tracking.prospect_id == prospect.id))

    phone = next((c.value for c in contacts if c.kind == "phone"), None)
    email = next((c.value for c in contacts if c.kind == "email"), None)
    priority_by_offer = {}
    for offer in OFFER_ORDER:
        offer_score = next((s.value for s in scores if s.offer == offer), None)
        value, reasons = _priority(prospect, lat, long, offer_score, phone, email)
        priority_by_offer[offer] = PriorityOut(
            value=value, reasons=[ReasonOut(**dataclasses.asdict(r)) for r in reasons]
        )

    return ProspectDetail(
        id=prospect.id,
        siret=prospect.siret,
        name=prospect.name,
        naf=prospect.naf,
        effectif_code=prospect.effectif_code,
        created_on=prospect.created_on,
        address=prospect.address,
        city=city_of(prospect.address),
        lat=lat,
        long=long,
        is_individual=prospect.is_individual,
        opposed_to_prospecting=prospect.opposed_to_prospecting,
        first_seen_at=prospect.first_seen_at,
        last_collected_at=prospect.last_collected_at,
        contacts=[
            ContactOut(kind=c.kind, value=c.value, source=c.source, seen_on=c.seen_on) for c in contacts
        ],
        site_analysis=SiteAnalysisOut.model_validate(analysis, from_attributes=True) if analysis else None,
        scores=[
            ScoreOut(offer=s.offer, value=s.value, tier=s.tier, reasons=[ReasonOut(**r) for r in s.reasons])
            for s in scores
        ],
        priority=priority_by_offer[Offer.WEB.value],
        priority_by_offer=priority_by_offer,
        tracking=TrackingOut(
            status=tracking.status if tracking else Status.NEW.value,
            favorite=tracking.favorite if tracking else False,
            notes=tracking.notes if tracking else "",
            updated_at=tracking.updated_at if tracking else None,
        ),
    )
