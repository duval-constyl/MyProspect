"""Contact priority: who to contact first (V1 plan, Task 8).

value = round(0.5 x opportunity) + bonuses, capped at 100. Readable rules, no model.
"""

from app.domain import Reason

MAX_PRIORITY = 100
PHONE_BONUS = 12
EMAIL_BONUS = 8
SMALL_STRUCTURE_BONUS = 8
NEARBY_BONUS = 6
NEARBY_MAX_KM = 20
# INSEE headcount bands: NN = no employee data, 00 = 0, 01 = 1-2, 02 = 3-5 employees.
SMALL_STRUCTURE_CODES = {None, "", "NN", "00", "01", "02"}


def contact_priority(
    opportunity: int,
    has_phone: bool,
    has_email: bool,
    effectif_code: str | None,
    distance_km_from_home: float | None,
) -> tuple[int, list[Reason]]:
    reasons = []
    base = round(0.5 * opportunity)
    if base:
        reasons.append(Reason("opportunity", f"Opportunité {opportunity}/100, comptée pour moitié", base))
    if has_phone:
        reasons.append(Reason("phone", "Téléphone connu", PHONE_BONUS))
    if has_email:
        reasons.append(Reason("email", "E-mail connu", EMAIL_BONUS))
    if effectif_code in SMALL_STRUCTURE_CODES:
        reasons.append(
            Reason("small_structure", "Petite structure : décideur facile à joindre", SMALL_STRUCTURE_BONUS)
        )
    if distance_km_from_home is not None and distance_km_from_home <= NEARBY_MAX_KM:
        reasons.append(
            Reason("nearby", f"À {distance_km_from_home:.0f} km de chez vous", NEARBY_BONUS)
        )
    value = min(MAX_PRIORITY, sum(reason.points for reason in reasons))
    return value, reasons
