"""CSV export of the prospects, with the same filters and order as the list."""

import csv
import io
from typing import Annotated

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from starlette.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app.analysis.screenshot import capture_site
from app.config import get_settings
from app.db import get_session
from app.domain import Offer
from app.report import render_audit_pdf
from app.routers.prospects import ProspectFilters, prospect_detail, prospect_filters, query_rows
from app.schemas import ProspectDetail

router = APIRouter()

SessionDep = Annotated[Session, Depends(get_session)]

COLUMNS = [
    "siret", "nom", "naf", "ville_adresse", "telephone", "email", "site",
    "score_web", "priorite", "statut", "favori", "notes",
    "opposee_prospection",  # not in the V1 plan: decided by Duval on 2026-11-25
]
STATUS_LABELS = {
    "new": "nouveau",
    "to_contact": "à contacter",
    "contacted": "contacté",
    "replied": "a répondu",
    "refused": "refusé",
}


def _yes_no(value: bool) -> str:
    return "oui" if value else "non"


FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")


def _cell(value: object) -> str:
    """Absent value -> empty cell, never "None".

    A value starting like a formula gets a leading apostrophe (OWASP advice against
    CSV injection): names, notes and contact details partly come from third parties,
    and Excel would otherwise read « +33 4 78 … » as a formula.
    """
    if value is None:
        return ""
    text = str(value)
    return f"'{text}" if text.startswith(FORMULA_STARTS) else text


@router.get("/exports/prospects.csv")
def export_prospects(
    session: SessionDep, filters: Annotated[ProspectFilters, Depends(prospect_filters)]
) -> Response:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(COLUMNS)
    for row in query_rows(session, filters):
        prospect = row.prospect
        writer.writerow(
            [
                prospect.siret,
                _cell(prospect.name),
                prospect.naf,
                _cell(prospect.address),
                _cell(row.phone),
                _cell(row.email),
                _cell(row.website),
                _cell(row.score_web),
                row.priority,
                STATUS_LABELS.get(row.status, row.status),
                _yes_no(row.favorite),
                _cell(row.notes),
                _yes_no(prospect.opposed_to_prospecting),
            ]
        )
    # UTF-8 with BOM so that spreadsheet software shows accents correctly.
    return Response(
        content=buffer.getvalue().encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="prospects.csv"'},
    )


async def audit_pdf_for(detail: ProspectDetail, offer: str) -> bytes:
    """The audit report PDF of a prospect, with the site screenshots when they are enabled."""
    screenshots = None
    if get_settings().screenshots_enabled and detail.site_analysis is not None:
        # A site that cannot be loaded gives placeholder text instead of images.
        screenshots = await capture_site(detail.site_analysis.url)
    return await run_in_threadpool(render_audit_pdf, detail, Offer(offer), screenshots)


@router.get("/prospects/{prospect_id}/audit.pdf")
async def audit_report(
    prospect_id: int, session: SessionDep, offer: Literal["web", "mobile", "cloud"] = "web"
) -> Response:
    """Audit report to attach to a first message (no private notes, no status)."""
    if not get_settings().audit_report_enabled:  # read before anything else
        raise HTTPException(404, "Rapport d'audit désactivé dans les réglages.")
    detail = prospect_detail(prospect_id, session)  # 404 if unknown
    pdf = await audit_pdf_for(detail, offer)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="audit-{detail.siret}-{offer}.pdf"'},
    )
