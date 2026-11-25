import pytest
from geoalchemy2 import WKTElement
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.models import Prospect, ScoreRow


def make_prospect(siret: str = "12345678900011", **overrides) -> Prospect:
    fields = {
        "siret": siret,
        "name": "Garage du Centre",
        "naf": "45.20A",
        "effectif_code": "01",
        "created_on": None,
        "geom": WKTElement("POINT(2.3522 48.8566)", srid=4326),
        "address": "1 rue de Rivoli 75001 Paris",
        "is_individual": False,
        "closed": False,
    }
    fields.update(overrides)
    return Prospect(**fields)


def test_prospect_roundtrip_with_geometry(db_session):
    db_session.add(make_prospect())
    db_session.commit()

    x, y = db_session.execute(
        select(func.ST_X(Prospect.geom), func.ST_Y(Prospect.geom))
    ).one()

    assert x == pytest.approx(2.3522)
    assert y == pytest.approx(48.8566)


def test_siret_is_unique(db_session):
    db_session.add(make_prospect())
    db_session.commit()

    db_session.add(make_prospect(name="Autre enseigne"))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_score_unique_per_offer(db_session):
    prospect = make_prospect()
    db_session.add(prospect)
    db_session.commit()
    reasons = [{"code": "no_site", "label": "Aucun site connu", "points": 75}]
    db_session.add_all(
        [
            ScoreRow(prospect_id=prospect.id, offer="web", value=75, tier=5, reasons=reasons),
            ScoreRow(prospect_id=prospect.id, offer="mobile", value=0, tier=1, reasons=[]),
        ]
    )
    db_session.commit()

    db_session.add(
        ScoreRow(prospect_id=prospect.id, offer="web", value=20, tier=2, reasons=[])
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
