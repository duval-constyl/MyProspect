"""SQLAlchemy models (V1 plan, Task 2)."""

from datetime import date, datetime

from geoalchemy2 import Geometry, WKBElement
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    false,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _one_of(column: str, values: tuple[str, ...]) -> str:
    allowed = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({allowed})"


CONTACT_KINDS = ("phone", "email", "website")
CONTACT_SOURCES = ("osm", "registry", "site")
OFFERS = ("web", "mobile", "cloud")
STATUSES = ("new", "to_contact", "contacted", "replied", "refused")
EXCLUSION_REASONS = ("deleted", "do_not_contact")
ZONE_KINDS = ("commune", "circle", "polygon")
JOB_STATES = ("pending", "running", "done", "failed")
CHANNELS = ("email", "call")
DRAFT_SOURCES = ("llm", "template")
EVENT_KINDS = ("status", "note", "followup")


class Prospect(Base):
    __tablename__ = "prospects"

    id: Mapped[int] = mapped_column(primary_key=True)
    siret: Mapped[str] = mapped_column(String(14), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    naf: Mapped[str] = mapped_column(String(10))
    effectif_code: Mapped[str | None] = mapped_column(String(4))
    created_on: Mapped[date | None] = mapped_column(Date)
    # Nullable: a company without coordinates is stored but not shown on the map.
    geom: Mapped[WKBElement | None] = mapped_column(
        Geometry("POINT", srid=4326, spatial_index=True), nullable=True
    )
    address: Mapped[str] = mapped_column(String(500), default="")
    is_individual: Mapped[bool] = mapped_column(Boolean, default=False)
    closed: Mapped[bool] = mapped_column(Boolean, default=False)
    # Not in the V1 plan: decided by Duval on 2026-11-25 (see docs/PROGRESS.md).
    opposed_to_prospecting: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false()
    )
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Contact(Base):
    __tablename__ = "contacts"
    __table_args__ = (
        UniqueConstraint("prospect_id", "kind", "value"),
        CheckConstraint(_one_of("kind", CONTACT_KINDS), name="contact_kind"),
        CheckConstraint(_one_of("source", CONTACT_SOURCES), name="contact_source"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    prospect_id: Mapped[int] = mapped_column(
        ForeignKey("prospects.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(16))
    value: Mapped[str] = mapped_column(String(500))
    source: Mapped[str] = mapped_column(String(16))
    seen_on: Mapped[date] = mapped_column(Date)


class SiteAnalysisRow(Base):
    __tablename__ = "site_analyses"

    id: Mapped[int] = mapped_column(primary_key=True)
    prospect_id: Mapped[int] = mapped_column(
        ForeignKey("prospects.id", ondelete="CASCADE"), unique=True
    )
    url: Mapped[str] = mapped_column(String(2048))
    reachable: Mapped[bool] = mapped_column(Boolean)
    https: Mapped[bool] = mapped_column(Boolean)
    has_title: Mapped[bool] = mapped_column(Boolean)
    has_description: Mapped[bool] = mapped_column(Boolean)
    has_h1: Mapped[bool] = mapped_column(Boolean)
    has_viewport: Mapped[bool] = mapped_column(Boolean)
    response_ms: Mapped[int | None] = mapped_column(Integer)
    tech: Mapped[list[str]] = mapped_column(ARRAY(String(32)), default=list)
    mobile_perf: Mapped[int | None] = mapped_column(Integer)
    analyzed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    has_booking: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    has_online_order: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())


class ScoreRow(Base):
    __tablename__ = "scores"
    __table_args__ = (
        UniqueConstraint("prospect_id", "offer"),
        CheckConstraint(_one_of("offer", OFFERS), name="score_offer"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    prospect_id: Mapped[int] = mapped_column(
        ForeignKey("prospects.id", ondelete="CASCADE"), index=True
    )
    offer: Mapped[str] = mapped_column(String(16))
    value: Mapped[int] = mapped_column(Integer)
    tier: Mapped[int] = mapped_column(Integer)
    reasons: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Tracking(Base):
    __tablename__ = "trackings"
    __table_args__ = (CheckConstraint(_one_of("status", STATUSES), name="tracking_status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    prospect_id: Mapped[int] = mapped_column(
        ForeignKey("prospects.id", ondelete="CASCADE"), unique=True
    )
    status: Mapped[str] = mapped_column(String(16), default="new")
    favorite: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Exclusion(Base):
    __tablename__ = "exclusions"
    __table_args__ = (
        CheckConstraint(_one_of("reason", EXCLUSION_REASONS), name="exclusion_reason"),
    )

    siret: Mapped[str] = mapped_column(String(14), primary_key=True)
    reason: Mapped[str] = mapped_column(String(32))
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Zone(Base):
    __tablename__ = "zones"
    __table_args__ = (CheckConstraint(_one_of("kind", ZONE_KINDS), name="zone_kind"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(16))
    geojson: Mapped[dict] = mapped_column(JSONB)
    naf_codes: Mapped[list[str]] = mapped_column(ARRAY(String(10)), default=list)
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (CheckConstraint(_one_of("state", JOB_STATES), name="job_state"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    zone_id: Mapped[int] = mapped_column(ForeignKey("zones.id", ondelete="CASCADE"), index=True)
    state: Mapped[str] = mapped_column(String(16), default="pending")
    done: Mapped[int] = mapped_column(Integer, default=0)
    total: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    # V3: start of the run; prospects collected before it were absent from this run.
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OutreachDraft(Base):
    """A draft e-mail or call script, never sent by the tool (V2 Task 6)."""

    __tablename__ = "outreach_drafts"
    __table_args__ = (
        CheckConstraint(_one_of("offer", OFFERS), name="draft_offer"),
        CheckConstraint(_one_of("channel", CHANNELS), name="draft_channel"),
        CheckConstraint(_one_of("source", DRAFT_SOURCES), name="draft_source"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    prospect_id: Mapped[int] = mapped_column(
        ForeignKey("prospects.id", ondelete="CASCADE"), index=True
    )
    offer: Mapped[str] = mapped_column(String(16))
    channel: Mapped[str] = mapped_column(String(16))
    subject: Mapped[str | None] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(16))
    # Which prompt or template produced it, for the reply statistics (V3).
    variant: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class FollowUp(Base):
    """A reminder to contact a prospect again on a given day (V2 Task 7)."""

    __tablename__ = "followups"

    id: Mapped[int] = mapped_column(primary_key=True)
    prospect_id: Mapped[int] = mapped_column(
        ForeignKey("prospects.id", ondelete="CASCADE"), index=True
    )
    due_on: Mapped[date] = mapped_column(Date, index=True)
    note: Mapped[str] = mapped_column(Text, default="")
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TrackingEvent(Base):
    """History of a prospect's follow-up: status, notes, reminders (V2 Task 7)."""

    __tablename__ = "tracking_events"
    __table_args__ = (CheckConstraint(_one_of("kind", EVENT_KINDS), name="event_kind"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    prospect_id: Mapped[int] = mapped_column(
        ForeignKey("prospects.id", ondelete="CASCADE"), index=True
    )
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    kind: Mapped[str] = mapped_column(String(16))
    text: Mapped[str] = mapped_column(Text)
