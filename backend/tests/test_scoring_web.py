from datetime import UTC, datetime

import pytest

from app.domain import Offer, SiteAnalysis
from app.scoring.web import score_web, tier_of


def analysis(**overrides) -> SiteAnalysis:
    fields = {
        "url": "https://garage-martin.fr/",
        "reachable": True,
        "https": True,
        "has_title": True,
        "has_description": True,
        "has_h1": True,
        "has_viewport": True,
        "response_ms": 300,
        "tech": [],
        "mobile_perf": 95,
        "analyzed_at": datetime(2026, 11, 25, tzinfo=UTC),
    }
    fields.update(overrides)
    return SiteAnalysis(**fields)


def codes(result) -> list[str]:
    return [reason.code for reason in result.reasons]


def test_no_site_scores_75_with_one_reason():
    result = score_web(has_known_site=False, analysis=None)

    assert result.offer == Offer.WEB
    assert result.value == 75
    assert codes(result) == ["no_site"]
    assert result.reasons[0].points == 75
    assert result.reasons[0].label == "Aucun site web connu"


def test_unreachable_site_scores_70():
    result = score_web(True, analysis(reachable=False, https=False, has_title=False,
                                      has_description=False, has_h1=False,
                                      has_viewport=False, mobile_perf=None))

    assert result.value == 70
    assert codes(result) == ["site_unreachable"]


def test_all_defects_caps_at_100():
    worst = analysis(https=False, has_title=False, has_description=False, has_h1=False,
                     has_viewport=False, mobile_perf=10)

    result = score_web(True, worst)

    # With the plan's points a reachable site sums to 70 at most: the cap is a safety net.
    assert codes(result) == ["no_https", "missing_seo_tags", "no_viewport", "slow_mobile"]
    assert result.value == 70
    assert result.value <= 100


def test_healthy_site_scores_0_with_no_reasons():
    result = score_web(True, analysis())

    assert result.value == 0
    assert result.reasons == []
    assert result.tier == 1


def test_missing_seo_tags_counted_once_and_named_in_label():
    result = score_web(True, analysis(has_title=False, has_h1=False))

    assert result.value == 15
    assert codes(result) == ["missing_seo_tags"]
    assert "titre" in result.reasons[0].label
    assert "H1" in result.reasons[0].label
    assert "description" not in result.reasons[0].label


@pytest.mark.parametrize(("perf", "points"), [(40, 20), (49, 20), (50, 10), (70, 10), (89, 10), (90, 0), (95, 0)])
def test_slow_mobile_tiers(perf, points):
    result = score_web(True, analysis(mobile_perf=perf))

    assert result.value == points
    assert ("slow_mobile" in codes(result)) == (points > 0)


def test_unknown_mobile_perf_adds_nothing():
    assert score_web(True, analysis(mobile_perf=None)).value == 0


def test_known_site_not_yet_analyzed_is_explained():
    result = score_web(True, None)

    assert result.value == 0
    assert codes(result) == ["site_not_analyzed"]
    assert result.reasons[0].points == 0


@pytest.mark.parametrize(("value", "tier"), [(0, 1), (16, 1), (17, 2), (33, 2), (34, 3), (84, 5), (85, 6), (100, 6)])
def test_tier_boundaries(value, tier):
    assert tier_of(value) == tier


@pytest.mark.parametrize(
    "site",
    [
        analysis(https=False),
        analysis(has_description=False, has_viewport=False),
        analysis(https=False, has_h1=False, mobile_perf=60),
    ],
)
def test_reasons_sum_matches_value_before_cap(site):
    result = score_web(True, site)

    assert sum(reason.points for reason in result.reasons) == result.value
    assert result.tier == tier_of(result.value)
    assert all(reason.label for reason in result.reasons)
