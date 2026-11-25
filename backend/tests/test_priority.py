import pytest

from app.scoring.priority import contact_priority


def codes(reasons) -> list[str]:
    return [reason.code for reason in reasons]


def test_base_is_half_of_opportunity():
    value, reasons = contact_priority(60, False, False, "12", None)

    assert value == 30
    assert codes(reasons) == ["opportunity"]
    assert reasons[0].points == 30


def test_zero_opportunity_without_bonus_has_no_reason():
    assert contact_priority(0, False, False, "12", None) == (0, [])


def test_phone_bonus_adds_12():
    value, reasons = contact_priority(60, True, False, "12", None)

    assert value == 30 + 12
    assert "phone" in codes(reasons)


def test_email_bonus_adds_8():
    value, reasons = contact_priority(60, False, True, "12", None)

    assert value == 30 + 8
    assert "email" in codes(reasons)


@pytest.mark.parametrize("effectif_code", [None, "", "NN", "00", "01", "02"])
def test_small_structure_bonus_adds_8(effectif_code):
    value, reasons = contact_priority(60, False, False, effectif_code, None)

    assert value == 30 + 8
    assert "small_structure" in codes(reasons)


@pytest.mark.parametrize("effectif_code", ["03", "11", "53"])
def test_larger_structure_has_no_small_bonus(effectif_code):
    value, reasons = contact_priority(60, False, False, effectif_code, None)

    assert value == 30
    assert "small_structure" not in codes(reasons)


@pytest.mark.parametrize("distance_km", [0, 12.5, 20])
def test_nearby_bonus_adds_6(distance_km):
    value, reasons = contact_priority(60, False, False, "12", distance_km)

    assert value == 30 + 6
    assert "nearby" in codes(reasons)


def test_beyond_20km_gives_no_bonus():
    value, reasons = contact_priority(60, False, False, "12", 20.1)

    assert value == 30
    assert "nearby" not in codes(reasons)


def test_unknown_distance_gives_no_bonus():
    value, reasons = contact_priority(60, False, False, "12", None)

    assert value == 30
    assert "nearby" not in codes(reasons)


def test_cap_at_100():
    value, reasons = contact_priority(100, True, True, "01", 3)

    # Highest possible with the plan's points: 50 + 12 + 8 + 8 + 6 = 84 (cap is a safety net).
    assert value == 84
    assert value <= 100
    assert codes(reasons) == ["opportunity", "phone", "email", "small_structure", "nearby"]


def test_cap_applies_when_sum_exceeds_100():
    value, _ = contact_priority(200, True, True, "01", 3)

    assert value == 100


def test_reasons_sum_to_value_and_are_labelled_in_french():
    value, reasons = contact_priority(75, True, False, "NN", 8)

    assert sum(reason.points for reason in reasons) == value
    assert all(reason.label for reason in reasons)
    assert {reason.code: reason.label for reason in reasons}["phone"] == "Téléphone connu"
