import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.modules.pricing import (
    DEFAULT_RATE_CARDS,
    BridalPackage,
    LineKind,
    PriceInputs,
    Region,
    ReviewFlag,
    TravelZone,
    price,
)
from app.modules.pricing.types import CustomLine

HI = DEFAULT_RATE_CARDS[Region.HAWAII]
OR = DEFAULT_RATE_CARDS[Region.OREGON]


def test_prd_hawaii_worked_example() -> None:
    # $325 + 2 x ($120 + $130) + $75 = $900, deposit $100, balance $800
    r = price(
        PriceInputs(
            Region.HAWAII,
            attendant_hair=2,
            attendant_makeup=2,
            travel_zone=TravelZone.OUTSIDE,
            stylists_required=1,
        ),
        HI,
    )
    assert (r.total_cents, r.deposit_cents, r.balance_cents) == (90_000, 10_000, 80_000)
    assert r.flags == ()


def test_prd_oregon_worked_example() -> None:
    # $500 + 2 x ($165 + $190) + $75 = $1,285, deposit $200, balance $1,085
    r = price(
        PriceInputs(
            Region.OREGON,
            attendant_hair=2,
            attendant_makeup=2,
            travel_zone=TravelZone.OUTSIDE,
            travel_fee_cents=7_500,
        ),
        OR,
    )
    assert (r.total_cents, r.deposit_cents, r.balance_cents) == (128_500, 20_000, 108_500)
    assert r.minimum_adjustment_cents == 0
    assert r.flags == ()


def test_oregon_minimum_adds_separate_line() -> None:
    r = price(PriceInputs(Region.OREGON, travel_zone=TravelZone.IN_TOWN), OR)
    assert r.subtotal_cents == 50_000
    assert r.minimum_adjustment_cents == 10_000
    assert r.total_cents == 60_000
    assert r.balance_cents == 40_000
    assert r.line_items[-1].kind == LineKind.MINIMUM_ADJUSTMENT


def test_hawaii_has_no_minimum() -> None:
    r = price(PriceInputs(Region.HAWAII, travel_zone=TravelZone.IN_TOWN), HI)
    assert r.total_cents == 32_500
    assert r.minimum_adjustment_cents == 0


def test_hawaii_travel_is_per_stylist() -> None:
    r = price(PriceInputs(Region.HAWAII, travel_zone=TravelZone.OUTSIDE, stylists_required=3), HI)
    travel = [li for li in r.line_items if li.kind == LineKind.TRAVEL][0]
    assert travel.amount_cents == 22_500


def test_hawaii_outside_without_stylist_count_is_blocked() -> None:
    r = price(PriceInputs(Region.HAWAII, travel_zone=TravelZone.OUTSIDE), HI)
    assert ReviewFlag.TRAVEL_UNCONFIRMED in r.flags
    assert not any(li.kind == LineKind.TRAVEL for li in r.line_items)


def test_unknown_travel_zone_is_flagged() -> None:
    assert ReviewFlag.TRAVEL_UNCONFIRMED in price(PriceInputs(Region.HAWAII), HI).flags
    assert ReviewFlag.TRAVEL_UNCONFIRMED in price(PriceInputs(Region.OREGON), OR).flags


@pytest.mark.parametrize("fee", [5_000, 10_500])
def test_oregon_travel_outside_range_is_flagged(fee: int) -> None:
    r = price(PriceInputs(Region.OREGON, travel_zone=TravelZone.OUTSIDE, travel_fee_cents=fee), OR)
    assert ReviewFlag.TRAVEL_OUT_OF_AREA in r.flags


def test_out_of_area_is_flagged_once() -> None:
    r = price(
        PriceInputs(Region.OREGON, travel_zone=TravelZone.OUT_OF_AREA, travel_fee_cents=20_000), OR
    )
    assert r.flags.count(ReviewFlag.TRAVEL_OUT_OF_AREA) == 1


@pytest.mark.parametrize("pkg", [BridalPackage.HAIR_ONLY, BridalPackage.MAKEUP_ONLY])
def test_partial_package_is_flagged(pkg: BridalPackage) -> None:
    r = price(PriceInputs(Region.HAWAII, bridal_package=pkg, travel_zone=TravelZone.IN_TOWN), HI)
    assert ReviewFlag.PARTIAL_BRIDAL_PACKAGE in r.flags


def test_attendants_without_bride_is_unusual() -> None:
    r = price(
        PriceInputs(
            Region.HAWAII,
            bridal_package=BridalPackage.NONE,
            attendant_hair=2,
            travel_zone=TravelZone.IN_TOWN,
        ),
        HI,
    )
    assert ReviewFlag.UNUSUAL_COMBINATION in r.flags


def test_large_party_and_custom_lines_are_unusual() -> None:
    big = price(PriceInputs(Region.HAWAII, attendant_hair=13, travel_zone=TravelZone.IN_TOWN), HI)
    assert ReviewFlag.UNUSUAL_COMBINATION in big.flags
    custom = price(
        PriceInputs(
            Region.HAWAII,
            travel_zone=TravelZone.IN_TOWN,
            custom_lines=(CustomLine("Flower girl hair", 6_000),),
        ),
        HI,
    )
    assert ReviewFlag.UNUSUAL_COMBINATION in custom.flags
    assert custom.total_cents == 38_500


def test_region_mismatch_raises() -> None:
    with pytest.raises(ValueError):
        price(PriceInputs(Region.OREGON), HI)


def test_negative_counts_rejected() -> None:
    with pytest.raises(ValueError):
        PriceInputs(Region.HAWAII, attendant_hair=-1)


def test_snapshot_is_independent_of_later_rate_changes() -> None:
    inputs = PriceInputs(Region.HAWAII, attendant_hair=1, travel_zone=TravelZone.IN_TOWN)
    snapshot = price(inputs, HI).to_snapshot()
    from dataclasses import replace

    raised = replace(HI, version=2, attendant_hair_cents=15_000)
    assert price(inputs, raised).total_cents == 47_500
    assert snapshot["total_cents"] == 44_500
    assert snapshot["rate_card_version"] == 1


inputs_strategy = st.builds(
    PriceInputs,
    region=st.sampled_from(list(Region)),
    attendant_hair=st.integers(0, 20),
    attendant_makeup=st.integers(0, 20),
    trial=st.booleans(),
    bridal_package=st.sampled_from(list(BridalPackage)),
    travel_zone=st.sampled_from(list(TravelZone)),
    stylists_required=st.one_of(st.none(), st.integers(0, 6)),
    travel_fee_cents=st.one_of(st.none(), st.integers(0, 30_000)),
)


@given(inputs_strategy)
def test_invariants(inputs: PriceInputs) -> None:
    r = price(inputs, DEFAULT_RATE_CARDS[inputs.region])
    assert sum(li.amount_cents for li in r.line_items) == r.total_cents
    assert r.balance_cents == r.total_cents - r.deposit_cents
    assert r.balance_cents >= 0
    if inputs.region == Region.OREGON:
        assert r.total_cents >= 60_000
    for li in r.line_items:
        assert li.amount_cents == li.quantity * li.unit_cents
