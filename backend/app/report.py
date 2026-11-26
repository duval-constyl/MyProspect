"""Audit report for a prospect, to attach to a first message (V3 plan, Task 3).

The report only uses what the prospect may read: name, city, the chosen offer's score
and reasons, the site's key figures and the sender's signature. Never the private
notes, the status, the favourite flag, the internal priority or other prospects.
"""

import base64
import os
from datetime import date

from jinja2 import Environment, PackageLoader, select_autoescape

from app.config import get_settings
from app.domain import Offer
from app.schemas import ProspectDetail

_templates = Environment(loader=PackageLoader("app", "templates"), autoescape=select_autoescape(["html"]))

OFFER_TITLES = {
    "web": "présence en ligne",
    "mobile": "réservation et commande sur mobile",
    "cloud": "outils numériques",
}
TIER_COLORS = ["#8d99ae", "#4f7cac", "#2a9d8f", "#e9c46a", "#f4a261", "#d62828"]
# A sentence for the prospect, in plain words, next to each reason.
EXPLANATIONS = {
    "no_site": "Vos futurs clients ne peuvent pas vous découvrir ni vous contacter en ligne.",
    "site_unreachable": "Un visiteur qui tente d'ouvrir votre site risque de repartir sans vous joindre.",
    "no_https": "Les navigateurs affichent les sites sans HTTPS comme « non sécurisés », ce qui inquiète les visiteurs.",
    "missing_seo_tags": "Ces balises aident les moteurs de recherche à présenter votre site dans leurs résultats.",
    "no_viewport": "Sur téléphone, la page s'affiche en miniature et oblige à zoomer.",
    "slow_mobile": "Une page lente sur téléphone fait partir une partie des visiteurs avant l'affichage.",
    "no_online_booking": "Vos clients doivent appeler pendant vos heures d'ouverture pour réserver.",
    "no_online_order": "Vos clients ne peuvent pas commander à distance.",
    "no_site_for_mobile": "Rien ne permet de réserver ou de commander depuis un téléphone.",
    "not_mobile_ready": "Sur téléphone, la page s'affiche en miniature et oblige à zoomer.",
    "outdated_tech": "Une technologie ancienne reçoit moins de correctifs de sécurité.",
}


def _yes_no(value: bool) -> str:
    return "oui" if value else "non"


def _response_time(ms: int | None) -> str:
    return "non mesuré" if ms is None else f"{ms / 1000:.1f} s".replace(".", ",")


def _data_uri(png: bytes | None) -> str | None:
    return f"data:image/png;base64,{base64.b64encode(png).decode()}" if png else None


def audit_context(detail: ProspectDetail, offer: Offer, screenshots=None) -> dict:
    settings = get_settings()
    score = next((s for s in detail.scores if s.offer == offer.value), None)
    site = detail.site_analysis
    sender = ", ".join(p for p in (settings.sender_name, settings.sender_business) if p) or "[votre nom], [votre activité]"
    return {
        "company": detail.name,
        "city": detail.city.title() if detail.city else None,
        "offer_title": OFFER_TITLES[offer.value],
        "report_date": date.today().strftime("%d/%m/%Y"),
        "score": score.value if score else None,
        "tier": score.tier if score else None,
        "tier_color": TIER_COLORS[(score.tier - 1) if score and 1 <= score.tier <= 6 else 0],
        "reasons": [
            {"label": r.label, "explanation": EXPLANATIONS.get(r.code)} for r in (score.reasons if score else [])
        ],
        "site": {
            "url": site.url,
            "reachable": site.reachable,
            "https": _yes_no(site.https),
            "mobile": _yes_no(site.has_viewport),
            "response_time": _response_time(site.response_ms),
            "mobile_perf": f"{site.mobile_perf}/100" if site.mobile_perf is not None else "non mesurée",
            "analyzed_on": site.analyzed_at.strftime("%d/%m/%Y"),
        }
        if site
        else None,
        "screenshots": {"desktop": _data_uri(screenshots.desktop_png), "mobile": _data_uri(screenshots.mobile_png)}
        if screenshots is not None
        else None,
        "sender": sender,
    }


def render_audit_html(detail: ProspectDetail, offer: Offer, screenshots=None) -> str:
    """`screenshots`: Screenshots of the home page, or None for no screenshot section."""
    return _templates.get_template("audit.html").render(**audit_context(detail, Offer(offer), screenshots))


def render_audit_pdf(detail: ProspectDetail, offer: Offer, screenshots=None) -> bytes:
    return _html_to_pdf(render_audit_html(detail, offer, screenshots))


def _html_to_pdf(html: str) -> bytes:
    # On Windows outside Docker, WeasyPrint needs GTK libraries (e.g. Inkscape's).
    directories = get_settings().weasyprint_dll_directories
    if directories and "WEASYPRINT_DLL_DIRECTORIES" not in os.environ:
        os.environ["WEASYPRINT_DLL_DIRECTORIES"] = directories
    from weasyprint import HTML

    return HTML(string=html).write_pdf()
