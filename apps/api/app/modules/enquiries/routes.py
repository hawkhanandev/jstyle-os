from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.modules.auth.deps import Account
from app.modules.enquiries import service
from app.modules.enquiries.models import Enquiry, Pipeline, PipelineHistory
from app.modules.enquiries.pipeline import TransitionBlocked, transition
from app.modules.enquiries.region import detect_region
from app.modules.platform.audit import write_audit
from app.modules.pricing.types import BridalPackage, Region, TravelZone

router = APIRouter(prefix="/enquiries", tags=["enquiries"])
DB = Annotated[Session, Depends(get_session)]


class EnquiryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    type: str
    pipeline_status: str
    closed_reason: str | None
    region: str | None
    timezone: str | None
    client_name: str
    email: str
    phone: str | None
    preferred_contact: str | None
    wedding_date: date | None
    venue_name: str | None
    venue_address: str | None
    wedding_type: str | None
    bridal_package: str | None
    attendant_hair_count: int
    attendant_makeup_count: int
    trial_requested: bool
    travel_zone: str | None
    stylists_required: int | None
    travel_notes: str | None
    notes: str | None
    services: dict[str, Any] | None
    needs_review_flags: list[str]
    created_at: datetime


class HistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    from_status: str | None
    to_status: str
    reason: str | None
    at: datetime


class EnquiryDetail(EnquiryOut):
    history: list[HistoryOut]


def _get(db: Session, enquiry_id: uuid.UUID) -> Enquiry:
    e = db.get(Enquiry, enquiry_id)
    if e is None:
        raise HTTPException(404, detail={"code": "not_found", "message": "Enquiry not found."})
    return e


@router.get("")
def list_enquiries(
    account: Account,
    db: DB,
    status: Pipeline | None = None,
    region: Region | None = None,
    q: str | None = None,
) -> list[EnquiryOut]:
    rows = service.search(
        db, status=status.value if status else None, region=region.value if region else None, q=q
    )
    return [EnquiryOut.model_validate(r) for r in rows]


@router.get("/{enquiry_id}")
def get_enquiry(enquiry_id: uuid.UUID, account: Account, db: DB) -> EnquiryDetail:
    e = _get(db, enquiry_id)
    history = db.scalars(
        select(PipelineHistory)
        .where(PipelineHistory.enquiry_id == e.id)
        .order_by(PipelineHistory.at)
    ).all()
    return EnquiryDetail(
        **EnquiryOut.model_validate(e).model_dump(),
        history=[HistoryOut.model_validate(h) for h in history],
    )


class EnquiryPatch(BaseModel):
    """Details only. Status changes go through the action endpoints."""

    client_name: str | None = Field(default=None, min_length=1, max_length=200)
    phone: str | None = None
    preferred_contact: str | None = None
    wedding_date: date | None = None
    region: Region | None = None
    venue_name: str | None = None
    venue_address: str | None = None
    wedding_type: str | None = None
    bridal_package: BridalPackage | None = None
    attendant_hair_count: int | None = Field(default=None, ge=0, le=50)
    attendant_makeup_count: int | None = Field(default=None, ge=0, le=50)
    trial_requested: bool | None = None
    travel_zone: TravelZone | None = None
    stylists_required: int | None = Field(default=None, ge=0, le=20)
    travel_notes: str | None = None
    notes: str | None = None


@router.patch("/{enquiry_id}")
def patch_enquiry(
    enquiry_id: uuid.UUID, body: EnquiryPatch, account: Account, db: DB
) -> EnquiryOut:
    e = _get(db, enquiry_id)
    changes = body.model_dump(exclude_unset=True, mode="json")
    before = {k: _jsonable(getattr(e, k)) for k in changes}
    for k, v in changes.items():
        setattr(e, k, v)
    if "region" in changes:
        region = detect_region(e.region)
        e.timezone = service.TIMEZONES.get(region) if region else None
        e.needs_review_flags = [f for f in e.needs_review_flags if f != "region_unknown"] + (
            [] if region else ["region_unknown"]
        )
    write_audit(
        db,
        account.actor,
        "enquiry.update",
        entity_type="enquiry",
        entity_id=e.id,
        before=before,
        after=changes,
    )
    db.commit()
    return EnquiryOut.model_validate(e)


def _jsonable(v: Any) -> Any:
    return v.isoformat() if isinstance(v, date) else v


class ReasonIn(BaseModel):
    reason: str | None = Field(default=None, max_length=2000)


def _act(
    db: Session, e: Enquiry, target: Pipeline, account: Account, reason: str | None
) -> EnquiryOut:
    try:
        transition(db, e, target, account.actor, reason=reason)
    except TransitionBlocked as exc:
        raise HTTPException(
            409, detail={"code": "transition_blocked", "message": str(exc), "details": exc.missing}
        ) from exc
    db.commit()
    return EnquiryOut.model_validate(e)


@router.post("/{enquiry_id}/start-review")
def start_review(enquiry_id: uuid.UUID, account: Account, db: DB) -> EnquiryOut:
    return _act(db, _get(db, enquiry_id), Pipeline.UNDER_REVIEW, account, None)


@router.post("/{enquiry_id}/request-info")
def request_info(enquiry_id: uuid.UUID, body: ReasonIn, account: Account, db: DB) -> EnquiryOut:
    return _act(db, _get(db, enquiry_id), Pipeline.NEEDS_INFORMATION, account, body.reason)


@router.post("/{enquiry_id}/mark-lost")
def mark_lost(enquiry_id: uuid.UUID, body: ReasonIn, account: Account, db: DB) -> EnquiryOut:
    return _act(db, _get(db, enquiry_id), Pipeline.LOST_DECLINED, account, body.reason)


@router.post("/{enquiry_id}/mark-expired")
def mark_expired(enquiry_id: uuid.UUID, body: ReasonIn, account: Account, db: DB) -> EnquiryOut:
    return _act(db, _get(db, enquiry_id), Pipeline.EXPIRED, account, body.reason)


@router.post("/{enquiry_id}/reopen")
def reopen(enquiry_id: uuid.UUID, account: Account, db: DB) -> EnquiryOut:
    return _act(db, _get(db, enquiry_id), Pipeline.UNDER_REVIEW, account, None)
