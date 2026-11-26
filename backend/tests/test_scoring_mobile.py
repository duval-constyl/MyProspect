from datetime import UTC, datetime

import pytest

from app.domain import Offer, SiteAnalysis
from app.scoring.mobile import BOOKING_NAF, ORDER_NAF, score_mobile

HAIRDRESSER, RESTAURANT, GARAGE, PLUMBER = "96.02A", "56.10A", "45.20A", "43.22A"


def site(**overrides) -> SiteAnalysis:
    fields = {
        "url": "https://exemple.fr/",
        "reachable": True,
        "https": True,
        "has_title": True,
        "has_description": True,
        "has_h1": True,
        "has_viewport": True,
        "response_ms": 200,
        "tech": [],
        "mobile_perf": None,
        "analyzed_at": datetime(2026, 11, 25, tzinfo=UTC),
        "has_booking": False,
        "has_online_order": False,
    }
    fields.update(overrides)
    return SiteAnalysis(**fields)


def codes(result) -> list[str]:
    return [reason.code for reason in result.reasons]


def test_naf_lists_match_the_plan():
    assert BOOKING_NAF == frozenset({"56.10A", "56.10C", "96.02A", "96.02B", "96.04Z", "45.20A"})
    assert ORDER_NAF == frozenset({"56.10A", "56.10C"})


def test_naf_outside_list_scores_zero_no_reasons():
    result = score_mobile(PLUMBER, False, None)

    assert (result.offer, result.value, result.tier, result.reasons) == (Offer.MOBILE, 0, 1, [])


def test_hairdresser_without_site_scores_70():
    result = score_mobile(HAIRDRESSER, False, None)

    assert result.value == 70
    assert codes(result) == ["no_online_booking", "no_site_for_mobile"]


def test_restaurant_without_booking_or_order_with_site_scores_70():
    result = score_mobile(RESTAURANT, True, site())

    assert result.value == 70
    assert codes(result) == ["no_online_booking", "no_online_order"]


def test_restaurant_with_booking_and_order_scores_0():
    result = score_mobile(RESTAURANT, True, site(has_booking=True, has_online_order=True))

    assert (result.value, result.reasons) == (0, [])


def test_garage_site_without_viewport_adds_10():
    result = score_mobile(GARAGE, True, site(has_viewport=False))

    assert result.value == 50 + 10
    assert codes(result) == ["no_online_booking", "not_mobile_ready"]


def test_unreachable_site_counts_as_no_booking_but_not_as_not_mobile_ready():
    result = score_mobile(HAIRDRESSER, True, site(reachable=False, has_viewport=False))

    assert codes(result) == ["no_online_booking"]
    assert result.value == 50


def test_cap_100():
    worst = score_mobile(RESTAURANT, False, None)

    # Highest possible with the plan's points: 50 + 20 + 20 = 90 (the cap is a safety net).
    assert worst.value == 90
    assert worst.value <= 100
    assert worst.tier == 6


@pytest.mark.parametrize("naf", sorted(BOOKING_NAF))
def test_reasons_sum_to_value_with_french_labels(naf):
    result = score_mobile(naf, True, site(has_viewport=False))

    assert sum(r.points for r in result.reasons) == result.value
    assert all(r.label for r in result.reasons)
