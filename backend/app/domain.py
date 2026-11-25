"""Shared domain types (see the V1 plan, section « Types partagés »)."""

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum


class Offer(StrEnum):
    WEB = "web"
    MOBILE = "mobile"
    CLOUD = "cloud"


class Status(StrEnum):
    NEW = "new"
    TO_CONTACT = "to_contact"
    CONTACTED = "contacted"
    REPLIED = "replied"
    REFUSED = "refused"


@dataclass(frozen=True)
class Reason:
    code: str
    label: str
    points: int


@dataclass(frozen=True)
class ScoreResult:
    offer: Offer
    value: int
    tier: int
    reasons: list[Reason]


@dataclass(frozen=True)
class Circle:
    lat: float
    long: float
    radius_km: float


@dataclass(frozen=True)
class RegistryCompany:
    siret: str
    name: str
    naf: str
    effectif_code: str | None
    created_on: date | None
    lat: float | None
    long: float | None
    address: str
    is_individual: bool
    closed: bool
    # Not in the V1 plan: decided by Duval on 2026-11-25 (see docs/PROGRESS.md).
    opposed_to_prospecting: bool = False


@dataclass(frozen=True)
class OsmBusiness:
    osm_id: str
    name: str
    lat: float
    long: float
    phone: str | None
    email: str | None
    website: str | None


@dataclass(frozen=True)
class SiteAnalysis:
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
