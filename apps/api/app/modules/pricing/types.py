from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class Region(StrEnum):
    HAWAII = "HI"
    OREGON = "OR"


class BridalPackage(StrEnum):
    FULL = "full"  # bridal hair and makeup
    HAIR_ONLY = "hair_only"
    MAKEUP_ONLY = "makeup_only"
    NONE = "none"


class TravelZone(StrEnum):
    IN_TOWN = "in_town"  # Hawaii: town/Waikiki. Oregon: no travel fee
    OUTSIDE = "outside"  # inside the service area but travel is charged
    OUT_OF_AREA = "out_of_area"  # beyond the defined zones: manual review
    UNKNOWN = "unknown"  # not yet confirmed by staff


class LineKind(StrEnum):
    PACKAGE = "package"
    ATTENDANT_HAIR = "attendant_hair"
    ATTENDANT_MAKEUP = "attendant_makeup"
    TRIAL = "trial"
    TRAVEL = "travel"
    CUSTOM = "custom"
    MINIMUM_ADJUSTMENT = "minimum_adjustment"


class ReviewFlag(StrEnum):
    PARTIAL_BRIDAL_PACKAGE = "partial_bridal_package"
    UNUSUAL_COMBINATION = "unusual_combination"
    TRAVEL_UNCONFIRMED = "travel_unconfirmed"
    TRAVEL_OUT_OF_AREA = "travel_out_of_area"


@dataclass(frozen=True)
class CustomLine:
    description: str
    amount_cents: int
    quantity: int = 1


@dataclass(frozen=True)
class PriceInputs:
    region: Region
    attendant_hair: int = 0
    attendant_makeup: int = 0
    trial: bool = False
    bridal_package: BridalPackage = BridalPackage.FULL
    travel_zone: TravelZone = TravelZone.UNKNOWN
    # Hawaii: staff-confirmed number of stylists travelling outside town/Waikiki.
    stylists_required: int | None = None
    # Oregon: staff-entered travel fee in cents (validated against the rate card range).
    travel_fee_cents: int | None = None
    custom_lines: tuple[CustomLine, ...] = ()

    def __post_init__(self) -> None:
        if self.attendant_hair < 0 or self.attendant_makeup < 0:
            raise ValueError("attendant counts cannot be negative")
        if self.stylists_required is not None and self.stylists_required < 0:
            raise ValueError("stylists_required cannot be negative")
        if self.travel_fee_cents is not None and self.travel_fee_cents < 0:
            raise ValueError("travel_fee_cents cannot be negative")


@dataclass(frozen=True)
class LineItem:
    kind: LineKind
    description: str
    quantity: int
    unit_cents: int
    amount_cents: int


@dataclass(frozen=True)
class PriceResult:
    region: Region
    rate_card_version: int
    line_items: tuple[LineItem, ...]
    subtotal_cents: int
    minimum_adjustment_cents: int
    total_cents: int
    deposit_cents: int
    balance_cents: int
    flags: tuple[ReviewFlag, ...] = field(default_factory=tuple)

    @property
    def needs_review(self) -> bool:
        """True when any flag must be acknowledged before the quote can be approved."""
        return bool(self.flags)

    def to_snapshot(self) -> dict[str, Any]:
        """JSON-safe snapshot stored on the quote. Never recomputed after creation."""
        return asdict(self)
