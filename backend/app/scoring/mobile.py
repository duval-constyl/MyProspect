"""Mobile opportunity score (0-100) with its reasons (V2 plan, Task 2).

Only trades that take bookings or orders are concerned: the score tells whether
a booking or ordering app (or mobile web flow) is missing.
"""

from app.domain import Offer, Reason, ScoreResult, SiteAnalysis
from app.scoring.web import tier_of

# Restaurants, hairdressers, beauty care, garages: they take bookings.
BOOKING_NAF: frozenset[str] = frozenset({"56.10A", "56.10C", "96.02A", "96.02B", "96.04Z", "45.20A"})
# Restaurants also take orders.
ORDER_NAF: frozenset[str] = frozenset({"56.10A", "56.10C"})

MAX_SCORE = 100
NO_ONLINE_BOOKING = 50
NO_ONLINE_ORDER = 20
NO_SITE_FOR_MOBILE = 20
NOT_MOBILE_READY = 10


def score_mobile(naf: str, has_known_site: bool, analysis: SiteAnalysis | None) -> ScoreResult:
    reasons = _reasons(naf, has_known_site, analysis)
    value = min(MAX_SCORE, sum(reason.points for reason in reasons))
    return ScoreResult(offer=Offer.MOBILE, value=value, tier=tier_of(value), reasons=reasons)


def _reasons(naf: str, has_known_site: bool, analysis: SiteAnalysis | None) -> list[Reason]:
    if naf not in BOOKING_NAF:
        return []
    # Without a site, or when it could not be read, booking and ordering are not detected.
    readable = has_known_site and analysis is not None and analysis.reachable
    has_booking = readable and analysis.has_booking
    has_order = readable and analysis.has_online_order

    reasons = []
    if not has_booking:
        reasons.append(
            Reason("no_online_booking", "Aucune réservation ni prise de rendez-vous en ligne détectée", NO_ONLINE_BOOKING)
        )
    if naf in ORDER_NAF and not has_order:
        reasons.append(Reason("no_online_order", "Aucune commande en ligne détectée", NO_ONLINE_ORDER))
    if not has_known_site:
        reasons.append(
            Reason("no_site_for_mobile", "Aucun site web connu : les clients ne peuvent ni réserver ni commander en ligne", NO_SITE_FOR_MOBILE)
        )
    elif readable and not analysis.has_viewport:
        reasons.append(
            Reason("not_mobile_ready", "Site non adapté au mobile (pas de balise viewport)", NOT_MOBILE_READY)
        )
    return reasons
