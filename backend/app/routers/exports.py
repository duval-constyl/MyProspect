"""CSV export of the prospects, with the same filters and order as the list."""

import csv
import io
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.db import get_session
from app.routers.prospects import ProspectFilters, prospect_filters, query_rows

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


def _cell(value: object) -> str:
    """Absent value -> empty cell, never "None"."""
    return "" if value is None else str(value)


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
                prospect.name,
                prospect.naf,
                prospect.address,
                _cell(row.phone),
                _cell(row.email),
                _cell(row.website),
                _cell(row.score),
                row.priority,
                STATUS_LABELS.get(row.status, row.status),
                _yes_no(row.favorite),
                row.notes,
                _yes_no(prospect.opposed_to_prospecting),
            ]
        )
    # UTF-8 with BOM so that spreadsheet software shows accents correctly.
    return Response(
        content=buffer.getvalue().encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="prospects.csv"'},
    )
