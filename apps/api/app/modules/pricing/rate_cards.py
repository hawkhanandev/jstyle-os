from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from app.modules.pricing.types import Region


@dataclass(frozen=True)
class RateCard:
    """One immutable version of a region's rates. All money in integer cents."""

    region: Region
    version: int
    package_cents: int
    attendant_hair_cents: int
    attendant_makeup_cents: int
    trial_cents: int
    deposit_cents: int
    # Hawaii: flat fee per stylist travelling outside town/Waikiki.
    travel_per_stylist_cents: int | None = None
    # Oregon: allowed range for the staff-entered travel fee.
    travel_min_cents: int | None = None
    travel_max_cents: int | None = None
    minimum_total_cents: int | None = None
    max_attendants_before_review: int = 12

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RateCard:
        return cls(**{**data, "region": Region(data["region"])})


HAWAII_V1 = RateCard(
    region=Region.HAWAII,
    version=1,
    package_cents=32_500,
    attendant_hair_cents=12_000,
    attendant_makeup_cents=13_000,
    trial_cents=25_000,
    deposit_cents=10_000,
    travel_per_stylist_cents=7_500,
)

OREGON_V1 = RateCard(
    region=Region.OREGON,
    version=1,
    package_cents=50_000,
    attendant_hair_cents=16_500,
    attendant_makeup_cents=19_000,
    trial_cents=22_500,
    deposit_cents=20_000,
    travel_min_cents=5_500,
    travel_max_cents=10_000,
    minimum_total_cents=60_000,
)

DEFAULT_RATE_CARDS: dict[Region, RateCard] = {Region.HAWAII: HAWAII_V1, Region.OREGON: OREGON_V1}
