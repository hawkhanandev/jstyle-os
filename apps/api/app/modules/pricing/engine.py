"""Pricing rules from the PRD, section 5.

Hawaii:  325 + 120h + 130m + 250t + 75 x stylists (outside town/Waikiki)
Oregon:  subtotal = 500 + 165h + 190m + 225t + travel ($55-$100, staff-entered)
         total = max(600, subtotal), shown as a separate minimum adjustment line
"""

from __future__ import annotations

from app.modules.pricing.rate_cards import RateCard
from app.modules.pricing.types import (
    BridalPackage,
    LineItem,
    LineKind,
    PriceInputs,
    PriceResult,
    Region,
    ReviewFlag,
    TravelZone,
)


def _line(kind: LineKind, description: str, quantity: int, unit_cents: int) -> LineItem:
    return LineItem(kind, description, quantity, unit_cents, quantity * unit_cents)


def _travel(inputs: PriceInputs, card: RateCard, flags: list[ReviewFlag]) -> LineItem | None:
    zone = inputs.travel_zone
    if zone == TravelZone.IN_TOWN:
        return None
    if zone == TravelZone.UNKNOWN:
        flags.append(ReviewFlag.TRAVEL_UNCONFIRMED)
        return None
    if zone == TravelZone.OUT_OF_AREA:
        flags.append(ReviewFlag.TRAVEL_OUT_OF_AREA)

    if card.region == Region.HAWAII:
        assert card.travel_per_stylist_cents is not None
        if not inputs.stylists_required:
            flags.append(ReviewFlag.TRAVEL_UNCONFIRMED)
            return None
        return _line(
            LineKind.TRAVEL,
            "Travel (per stylist)",
            inputs.stylists_required,
            card.travel_per_stylist_cents,
        )

    # Oregon: staff-entered fee validated against the rate card range.
    fee = inputs.travel_fee_cents
    if fee is None:
        flags.append(ReviewFlag.TRAVEL_UNCONFIRMED)
        return None
    lo, hi = card.travel_min_cents, card.travel_max_cents
    if (
        lo is not None
        and hi is not None
        and not lo <= fee <= hi
        and ReviewFlag.TRAVEL_OUT_OF_AREA not in flags
    ):
        flags.append(ReviewFlag.TRAVEL_OUT_OF_AREA)
    return _line(LineKind.TRAVEL, "Travel fee", 1, fee)


def price(inputs: PriceInputs, card: RateCard) -> PriceResult:
    if inputs.region != card.region:
        raise ValueError(f"rate card is for {card.region}, inputs are for {inputs.region}")

    flags: list[ReviewFlag] = []
    lines: list[LineItem] = []

    if inputs.bridal_package == BridalPackage.FULL:
        label = (
            "Bridal hair and makeup package"
            if card.region == Region.HAWAII
            else "Group bridal hair and makeup"
        )
        lines.append(_line(LineKind.PACKAGE, label, 1, card.package_cents))
    else:
        # No rate exists for partial packages: staff prices them with a custom line.
        flags.append(ReviewFlag.PARTIAL_BRIDAL_PACKAGE)

    if inputs.attendant_hair:
        lines.append(
            _line(
                LineKind.ATTENDANT_HAIR,
                "Attendant hair",
                inputs.attendant_hair,
                card.attendant_hair_cents,
            )
        )
    if inputs.attendant_makeup:
        lines.append(
            _line(
                LineKind.ATTENDANT_MAKEUP,
                "Attendant makeup",
                inputs.attendant_makeup,
                card.attendant_makeup_cents,
            )
        )
    if inputs.trial:
        lines.append(_line(LineKind.TRIAL, "Bridal trial", 1, card.trial_cents))

    travel = _travel(inputs, card, flags)
    if travel is not None:
        lines.append(travel)

    for custom in inputs.custom_lines:
        lines.append(
            _line(LineKind.CUSTOM, custom.description, custom.quantity, custom.amount_cents)
        )

    attendants = max(inputs.attendant_hair, inputs.attendant_makeup)
    unusual = (
        (inputs.bridal_package == BridalPackage.NONE and attendants > 0)
        or attendants > card.max_attendants_before_review
        or bool(inputs.custom_lines)
    )
    if unusual:
        flags.append(ReviewFlag.UNUSUAL_COMBINATION)

    subtotal = sum(li.amount_cents for li in lines)
    adjustment = 0
    if card.minimum_total_cents is not None and subtotal < card.minimum_total_cents:
        adjustment = card.minimum_total_cents - subtotal
        lines.append(
            LineItem(
                LineKind.MINIMUM_ADJUSTMENT, "Minimum booking adjustment", 1, adjustment, adjustment
            )
        )

    total = subtotal + adjustment
    deposit = min(card.deposit_cents, total)
    return PriceResult(
        region=card.region,
        rate_card_version=card.version,
        line_items=tuple(lines),
        subtotal_cents=subtotal,
        minimum_adjustment_cents=adjustment,
        total_cents=total,
        deposit_cents=deposit,
        balance_cents=total - deposit,
        flags=tuple(dict.fromkeys(flags)),
    )
