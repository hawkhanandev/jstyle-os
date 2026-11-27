import pytest

from app.modules.enquiries.region import detect_region, suggest_travel_zone
from app.modules.pricing.types import Region, TravelZone


@pytest.mark.parametrize(
    ("field", "text", "expected"),
    [
        ("Hawaii", None, Region.HAWAII),
        ("OR", None, Region.OREGON),
        (None, "Halekulani, 2199 Kalia Rd, Honolulu, HI 96815", Region.HAWAII),
        (None, "Kualoa Ranch 96730", Region.HAWAII),
        (None, "Skamania? no, Hood River OR 97031", Region.OREGON),
        (None, "The Allison Inn, Newberg", Region.OREGON),
        (None, "Somewhere in Texas 75001", None),
        (None, None, None),
    ],
)
def test_detect_region(field: str | None, text: str | None, expected: Region | None) -> None:
    assert detect_region(field, text) == expected


def test_travel_zone_suggestion() -> None:
    assert suggest_travel_zone(Region.HAWAII, "Waikiki Beach") == TravelZone.IN_TOWN
    assert suggest_travel_zone(Region.HAWAII, "Ko Olina 96707") == TravelZone.OUTSIDE
    assert suggest_travel_zone(Region.HAWAII, "a beach") == TravelZone.UNKNOWN
    assert suggest_travel_zone(Region.OREGON, "Portland 97201") == TravelZone.UNKNOWN
