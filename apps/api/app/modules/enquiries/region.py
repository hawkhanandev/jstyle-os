"""Region detection from the form's region field, ZIP code and place names. Pure function."""

from __future__ import annotations

import re

from app.modules.pricing.types import Region, TravelZone

HAWAII_WORDS = (
    "hawaii",
    "oahu",
    "o'ahu",
    "honolulu",
    "waikiki",
    "maui",
    "kauai",
    "kona",
    "kailua",
    "kapolei",
    "ko olina",
    "north shore",
    "haleiwa",
    "lanikai",
)
OREGON_WORDS = (
    "oregon",
    "portland",
    "bend",
    "eugene",
    "salem",
    "hood river",
    "ashland",
    "willamette",
    "cannon beach",
    "astoria",
    "newberg",
    "dundee",
)
ZIP = re.compile(r"\b(9\d{4})(?:-\d{4})?\b")

# Default "town/Waikiki" ZIPs for Hawaii (urban Honolulu). Editable in settings later;
# anything else on Oahu is "outside" and pays travel per stylist.
HONOLULU_TOWN_ZIPS = frozenset({"96813", "96814", "96815", "96816", "96817", "96822", "96826"})


def detect_region(region_field: str | None, *texts: str | None) -> Region | None:
    if region_field:
        v = region_field.strip().upper()
        if v in ("HI", "HAWAII"):
            return Region.HAWAII
        if v in ("OR", "OREGON"):
            return Region.OREGON
    blob = " ".join(t for t in texts if t).lower()
    for m in ZIP.finditer(blob):
        z = m.group(1)
        if z.startswith(("967", "968")):
            return Region.HAWAII
        if z.startswith("97"):
            return Region.OREGON
    if any(w in blob for w in HAWAII_WORDS):
        return Region.HAWAII
    if any(w in blob for w in OREGON_WORDS):
        return Region.OREGON
    return None


def suggest_travel_zone(region: Region | None, *texts: str | None) -> TravelZone:
    """A first guess for staff. Oregon travel is always confirmed by staff."""
    if region != Region.HAWAII:
        return TravelZone.UNKNOWN
    blob = " ".join(t for t in texts if t).lower()
    zips = {m.group(1) for m in ZIP.finditer(blob)}
    if zips & HONOLULU_TOWN_ZIPS or "waikiki" in blob:
        return TravelZone.IN_TOWN
    if zips:
        return TravelZone.OUTSIDE
    return TravelZone.UNKNOWN
