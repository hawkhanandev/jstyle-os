from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.modules.auth.deps import Account
from app.modules.pricing import service
from app.modules.pricing.engine import price
from app.modules.pricing.rate_cards import RateCard
from app.modules.pricing.types import (
    BridalPackage,
    CustomLine,
    PriceInputs,
    Region,
    TravelZone,
)

router = APIRouter(tags=["pricing"])
DB = Annotated[Session, Depends(get_session)]


class RateCardOut(BaseModel):
    id: uuid.UUID
    region: Region
    version: int
    effective_from: datetime
    is_active: bool
    note: str | None
    rates: dict[str, Any]


class RateCardIn(BaseModel):
    region: Region
    package_cents: int = Field(ge=0)
    attendant_hair_cents: int = Field(ge=0)
    attendant_makeup_cents: int = Field(ge=0)
    trial_cents: int = Field(ge=0)
    deposit_cents: int = Field(ge=0)
    travel_per_stylist_cents: int | None = Field(default=None, ge=0)
    travel_min_cents: int | None = Field(default=None, ge=0)
    travel_max_cents: int | None = Field(default=None, ge=0)
    minimum_total_cents: int | None = Field(default=None, ge=0)
    max_attendants_before_review: int = Field(default=12, ge=1)
    note: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _region_rules(self) -> RateCardIn:
        if self.region == Region.HAWAII and self.travel_per_stylist_cents is None:
            raise ValueError("Hawaii needs travel_per_stylist_cents")
        if self.region == Region.OREGON and (
            self.travel_min_cents is None or self.travel_max_cents is None
        ):
            raise ValueError("Oregon needs travel_min_cents and travel_max_cents")
        if (
            self.travel_min_cents is not None
            and self.travel_max_cents is not None
            and self.travel_min_cents > self.travel_max_cents
        ):
            raise ValueError("travel_min_cents must not exceed travel_max_cents")
        return self


def _out(row: Any) -> RateCardOut:
    return RateCardOut(
        id=row.id,
        region=Region(row.region),
        version=row.version,
        effective_from=row.effective_from,
        is_active=row.is_active,
        note=row.note,
        rates=row.rates,
    )


@router.get("/rate-cards")
def list_rate_cards(account: Account, db: DB) -> list[RateCardOut]:
    return [_out(r) for region in Region for r in service.history(db, region)]


@router.post("/rate-cards", status_code=201)
def create_rate_card(body: RateCardIn, account: Account, db: DB) -> RateCardOut:
    card = RateCard(**body.model_dump(exclude={"note"}), version=0)
    row = service.create_version(db, account.actor, card, note=body.note)
    db.commit()
    return _out(row)


class CustomLineIn(BaseModel):
    description: str = Field(min_length=1, max_length=200)
    amount_cents: int = Field(ge=0)
    quantity: int = Field(default=1, ge=1)


class PreviewIn(BaseModel):
    region: Region
    attendant_hair: int = Field(default=0, ge=0, le=50)
    attendant_makeup: int = Field(default=0, ge=0, le=50)
    trial: bool = False
    bridal_package: BridalPackage = BridalPackage.FULL
    travel_zone: TravelZone = TravelZone.UNKNOWN
    stylists_required: int | None = Field(default=None, ge=0, le=20)
    travel_fee_cents: int | None = Field(default=None, ge=0)
    custom_lines: list[CustomLineIn] = []


@router.post("/pricing/preview")
def preview(body: PreviewIn, account: Account, db: DB) -> dict[str, Any]:
    """Display only. Quotes store their own snapshot when created (Phase 3)."""
    try:
        _, card = service.active_card(db, body.region)
    except service.NoActiveRateCard as exc:
        raise HTTPException(
            409, detail={"code": "no_rate_card", "message": "No active rate card for this region."}
        ) from exc
    inputs = PriceInputs(
        **body.model_dump(exclude={"custom_lines"}),
        custom_lines=tuple(CustomLine(**c.model_dump()) for c in body.custom_lines),
    )
    return price(inputs, card).to_snapshot()
