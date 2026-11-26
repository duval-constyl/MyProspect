"""Duplicates and companies that disappeared (V3 plan, Task 1)."""

from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.geo import distance_m, point_in_zone
from app.models import Job, Prospect, Zone
from app.sources.osm import normalize_name
from app.sources.registry import registry_lookup_by_siret


def find_duplicates(session: Session, max_distance_m: int = 30) -> list[tuple[int, int]]:
    """Pairs (smaller id, larger id) of prospects with the same normalized name, close together."""
    rows = session.execute(
        select(Prospect.id, Prospect.name, func.ST_Y(Prospect.geom), func.ST_X(Prospect.geom))
        .where(Prospect.geom.is_not(None))
        .order_by(Prospect.id)
    ).all()
    by_name: dict[str, list[tuple[int, float, float]]] = defaultdict(list)
    for prospect_id, name, lat, long in rows:
        key = normalize_name(name)
        if key:
            by_name[key].append((prospect_id, lat, long))
    pairs = []
    for group in by_name.values():
        for index, (first_id, lat1, long1) in enumerate(group):
            for second_id, lat2, long2 in group[index + 1 :]:
                if distance_m(lat1, long1, lat2, long2) <= max_distance_m:
                    pairs.append((first_id, second_id))
    return sorted(pairs)


async def mark_closed(session: Session, zone_id: int, lookup=registry_lookup_by_siret) -> int:
    """Prospects of the zone absent from its last finished collection and declared closed
    by the registry are marked `closed=True`. Returns how many were marked.

    Absent = collected for the last time before that collection started. An unknown
    answer (registry down, company no longer public) keeps the prospect as it is.
    """
    zone = session.get(Zone, zone_id)
    started_at = session.scalar(
        select(Job.started_at)
        .where(Job.zone_id == zone_id, Job.state == "done", Job.started_at.is_not(None))
        .order_by(Job.started_at.desc())
        .limit(1)
    )
    if zone is None or started_at is None:
        return 0

    candidates = session.execute(
        select(Prospect, func.ST_Y(Prospect.geom).label("lat"), func.ST_X(Prospect.geom).label("long"))
        .where(
            Prospect.closed.is_(False),
            Prospect.geom.is_not(None),
            Prospect.last_collected_at < started_at,
            # Only the trades this zone collects: other trades were never searched here.
            Prospect.naf.in_(zone.naf_codes),
        )
    ).all()
    marked = 0
    for row in candidates:
        if not point_in_zone(zone.kind, zone.geojson, row.lat, row.long):
            continue
        if await lookup(row.Prospect.siret) == "closed":
            row.Prospect.closed = True
            marked += 1
    session.commit()
    return marked
