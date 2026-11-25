"""API response schemas. An absent value is null or an empty list, never a fake value."""

from datetime import date, datetime

from pydantic import BaseModel


class ReasonOut(BaseModel):
    code: str
    label: str
    points: int


class ProspectListItem(BaseModel):
    id: int
    siret: str
    name: str
    naf: str
    address: str
    city: str | None
    lat: float | None
    long: float | None
    score_web: int | None
    tier: int | None
    priority: int
    status: str
    favorite: bool
    has_site: bool
    phone: str | None
    email: str | None
    website: str | None
    opposed_to_prospecting: bool


class ProspectList(BaseModel):
    items: list[ProspectListItem]
    total: int


class Cluster(BaseModel):
    lat: float
    long: float
    count: int
    max_score: int | None
    tier: int | None
    prospect_id: int | None  # set when the cluster is a single prospect


class Clusters(BaseModel):
    clusters: list[Cluster]


class Stats(BaseModel):
    in_view: int
    with_site: int
    without_site: int


class ContactOut(BaseModel):
    kind: str
    value: str
    source: str
    seen_on: date


class SiteAnalysisOut(BaseModel):
    url: str
    reachable: bool
    https: bool
    has_title: bool
    has_description: bool
    has_h1: bool
    has_viewport: bool
    response_ms: int | None
    tech: list[str]
    mobile_perf: int | None
    analyzed_at: datetime


class ScoreOut(BaseModel):
    offer: str
    value: int
    tier: int
    reasons: list[ReasonOut]


class PriorityOut(BaseModel):
    value: int
    reasons: list[ReasonOut]


class TrackingOut(BaseModel):
    status: str
    favorite: bool
    notes: str
    updated_at: datetime | None


class ProspectDetail(BaseModel):
    id: int
    siret: str
    name: str
    naf: str
    effectif_code: str | None
    created_on: date | None
    address: str
    city: str | None
    lat: float | None
    long: float | None
    is_individual: bool
    opposed_to_prospecting: bool
    first_seen_at: datetime
    last_collected_at: datetime
    contacts: list[ContactOut]
    site_analysis: SiteAnalysisOut | None
    scores: list[ScoreOut]
    priority: PriorityOut
    tracking: TrackingOut
