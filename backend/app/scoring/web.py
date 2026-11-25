"""Web opportunity score (0-100) with its reasons (V1 plan, Task 7)."""

from app.domain import Offer, Reason, ScoreResult, SiteAnalysis

MAX_SCORE = 100

NO_SITE = 75
SITE_UNREACHABLE = 70
NO_HTTPS = 20
MISSING_SEO_TAGS = 15
NO_VIEWPORT = 15
VERY_SLOW_MOBILE = 20  # PageSpeed mobile < 50
SLOW_MOBILE = 10  # PageSpeed mobile 50-89


def tier_of(value: int) -> int:
    return min(6, value // 17 + 1)


def score_web(has_known_site: bool, analysis: SiteAnalysis | None) -> ScoreResult:
    reasons = _reasons(has_known_site, analysis)
    value = min(MAX_SCORE, sum(reason.points for reason in reasons))
    return ScoreResult(offer=Offer.WEB, value=value, tier=tier_of(value), reasons=reasons)


def _reasons(has_known_site: bool, analysis: SiteAnalysis | None) -> list[Reason]:
    if not has_known_site:
        return [Reason("no_site", "Aucun site web connu", NO_SITE)]
    if analysis is None:
        return [Reason("site_not_analyzed", "Site connu, pas encore analysé", 0)]
    if not analysis.reachable:
        return [Reason("site_unreachable", "Site web inaccessible", SITE_UNREACHABLE)]

    reasons = []
    if not analysis.https:
        reasons.append(Reason("no_https", "Site sans HTTPS (connexion non sécurisée)", NO_HTTPS))
    missing = [
        label
        for label, present in (
            ("titre", analysis.has_title),
            ("description", analysis.has_description),
            ("titre principal H1", analysis.has_h1),
        )
        if not present
    ]
    if missing:
        reasons.append(
            Reason(
                "missing_seo_tags",
                f"Balises de référencement manquantes : {', '.join(missing)}",
                MISSING_SEO_TAGS,
            )
        )
    if not analysis.has_viewport:
        reasons.append(
            Reason("no_viewport", "Site non adapté au mobile (pas de balise viewport)", NO_VIEWPORT)
        )
    perf = analysis.mobile_perf
    if perf is not None and perf < 90:
        points = VERY_SLOW_MOBILE if perf < 50 else SLOW_MOBILE
        reasons.append(Reason("slow_mobile", f"Site lent sur mobile (PageSpeed {perf}/100)", points))
    return reasons
