from datetime import UTC, date, datetime

import pytest

from app.domain import Offer, SiteAnalysis
from app.scoring.cloud import score_cloud

TODAY = date(2026, 11, 25)


def site(tech: list[str], reachable: bool = True) -> SiteAnalysis:
    return SiteAnalysis(
        url="https://exemple.fr/",
        reachable=reachable,
        https=True,
        has_title=True,
        has_description=True,
        has_h1=True,
        has_viewport=True,
        response_ms=200,
        tech=tech,
        mobile_perf=None,
        analyzed_at=datetime(2026, 11, 25, tzinfo=UTC),
    )


def codes(result) -> list[str]:
    return [reason.code for reason in result.reasons]


def cloud(analysis=None, effectif_code=None, created_on=None, hiring_tech=False):
    return score_cloud(effectif_code, created_on, analysis, TODAY, hiring_tech=hiring_tech)


def test_jquery_1_is_outdated_jquery_3_is_not():
    old = cloud(site(["jquery@1.12.4"]))
    recent = cloud(site(["jquery@3.7.1"]))

    assert (old.value, codes(old)) == (30, ["outdated_tech"])
    assert "jQuery 1.12.4" in old.reasons[0].label
    assert (recent.value, recent.reasons) == (0, [])


def test_wordpress_5_outdated():
    result = cloud(site(["wordpress@5.8", "jquery@3.6.0"]))

    assert (result.value, codes(result)) == (30, ["outdated_tech"])
    assert "WordPress 5.8" in result.reasons[0].label
    assert cloud(site(["wordpress@6.6"])).value == 0


def test_outdated_tech_counts_once_and_names_every_old_tool():
    result = cloud(site(["wordpress@4.9", "jquery@1.11.0"]))

    assert result.value == 30
    assert "WordPress 4.9" in result.reasons[0].label and "jQuery 1.11.0" in result.reasons[0].label


def test_unknown_version_or_unreachable_site_is_not_outdated():
    assert cloud(site(["wordpress", "jquery"])).value == 0
    assert cloud(site([], reachable=False)).value == 0
    assert cloud(site(["jquery@abc"])).value == 0


def test_recent_company_boundary():
    created_23_months_ago = date(2024, 12, 25)
    created_25_months_ago = date(2024, 10, 25)
    created_24_months_ago = date(2024, 11, 25)

    assert codes(cloud(created_on=created_23_months_ago)) == ["recent_company"]
    assert cloud(created_on=created_23_months_ago).value == 25
    assert cloud(created_on=created_25_months_ago).value == 0
    assert cloud(created_on=created_24_months_ago).value == 0  # « moins de 24 mois »


@pytest.mark.parametrize(("code", "points"), [("03", 20), ("11", 20), ("12", 20), ("21", 20), ("02", 0), ("22", 0), ("NN", 0)])
def test_mid_size_codes(code, points):
    result = cloud(effectif_code=code)

    assert result.value == points
    assert ("mid_size" in codes(result)) == (points > 0)


def test_hiring_flag_adds_25():
    result = cloud(hiring_tech=True)

    assert (result.value, codes(result)) == (25, ["hiring_tech"])


def test_all_unknown_inputs_scores_0_no_error():
    result = score_cloud(None, None, None, TODAY)

    assert (result.offer, result.value, result.tier, result.reasons) == (Offer.CLOUD, 0, 1, [])


def test_everything_reaches_exactly_100():
    result = cloud(site(["jquery@1.12.4"]), "12", date(2026, 1, 10), hiring_tech=True)

    assert result.value == 100
    assert codes(result) == ["outdated_tech", "recent_company", "mid_size", "hiring_tech"]
    assert sum(r.points for r in result.reasons) == 100
    assert result.tier == 6
