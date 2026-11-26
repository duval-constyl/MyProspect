"""Cloud and custom software opportunity score (0-100) with its reasons (V2 plan, Task 3)."""

from datetime import date

from app.domain import Offer, Reason, ScoreResult, SiteAnalysis
from app.scoring.web import tier_of

MAX_SCORE = 100
OUTDATED_TECH = 30
RECENT_COMPANY = 25
MID_SIZE = 20
HIRING_TECH = 25

RECENT_MONTHS = 24
# INSEE headcount bands 03 = 6-9, 11 = 10-19, 12 = 20-49, 21 = 50-99 employees.
MID_SIZE_CODES = frozenset({"03", "11", "12", "21"})
# Tool -> (display name, first major version that is not outdated).
CURRENT_MAJOR = {"jquery": ("jQuery", 3), "wordpress": ("WordPress", 6)}


def score_cloud(
    effectif_code: str | None,
    created_on: date | None,
    analysis: SiteAnalysis | None,
    today: date,
    hiring_tech: bool = False,
) -> ScoreResult:
    reasons = []
    outdated = _outdated_tools(analysis)
    if outdated:
        reasons.append(
            Reason("outdated_tech", f"Technologie vieillissante : {', '.join(outdated)}", OUTDATED_TECH)
        )
    months = _full_months_between(created_on, today) if created_on else None
    if months is not None and 0 <= months < RECENT_MONTHS:
        reasons.append(
            Reason("recent_company", f"Entreprise récente : créée il y a {months} mois", RECENT_COMPANY)
        )
    if effectif_code in MID_SIZE_CODES:
        reasons.append(
            Reason("mid_size", "Équipe de 6 à 99 salariés : des besoins d'outils internes", MID_SIZE)
        )
    if hiring_tech:
        reasons.append(Reason("hiring_tech", "Recrute sur un poste technique (offre d'emploi ouverte)", HIRING_TECH))

    value = min(MAX_SCORE, sum(reason.points for reason in reasons))
    return ScoreResult(offer=Offer.CLOUD, value=value, tier=tier_of(value), reasons=reasons)


def _outdated_tools(analysis: SiteAnalysis | None) -> list[str]:
    """Readable versions older than the current major ("jQuery 1.12.4 (avant la version 3)")."""
    if analysis is None or not analysis.reachable:
        return []
    outdated = []
    for entry in analysis.tech:
        name, _, version = entry.partition("@")
        if name not in CURRENT_MAJOR or not version:
            continue
        try:
            major = int(version.split(".")[0])
        except ValueError:
            continue
        label, current = CURRENT_MAJOR[name]
        if major < current:
            outdated.append(f"{label} {version} (avant la version {current})")
    return outdated


def _full_months_between(start: date, end: date) -> int:
    months = (end.year - start.year) * 12 + (end.month - start.month)
    return months - 1 if end.day < start.day else months
