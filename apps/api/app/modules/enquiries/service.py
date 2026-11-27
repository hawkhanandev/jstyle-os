from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.modules.enquiries.models import Enquiry, EnquiryType, Pipeline, PlannerCompany
from app.modules.enquiries.region import detect_region, suggest_travel_zone
from app.modules.platform.audit import Actor, write_audit
from app.modules.pricing.types import Region

TIMEZONES = {Region.HAWAII: "Pacific/Honolulu", Region.OREGON: "America/Los_Angeles"}


@dataclass
class EnquiryInput:
    type: EnquiryType
    client_name: str
    email: str
    phone: str | None = None
    preferred_contact: str | None = None
    wedding_date: date | None = None
    region: str | None = None
    venue_name: str | None = None
    venue_address: str | None = None
    wedding_type: str | None = None
    bridal_package: str | None = None
    attendant_hair_count: int = 0
    attendant_makeup_count: int = 0
    trial_requested: bool = False
    travel_notes: str | None = None
    notes: str | None = None
    # Planner form only
    planner_company: str | None = None
    planner_contact_name: str | None = None
    services: dict[str, Any] | None = None
    raw: dict[str, Any] = field(default_factory=dict)


def review_flags(region: Region | None, wedding_date: date | None, today: date) -> list[str]:
    flags = []
    if region is None:
        flags.append("region_unknown")
    if wedding_date is not None:
        if wedding_date < today:
            flags.append("date_in_past")
        elif wedding_date < today + timedelta(days=14):
            flags.append("date_under_14_days")
    return flags


def create_enquiry(db: Session, data: EnquiryInput, actor: Actor, *, today: date) -> Enquiry:
    """Only the public forms (and Spam review approval) call this."""
    region = detect_region(data.region, data.venue_address, data.venue_name, data.travel_notes)
    planner_id: uuid.UUID | None = None
    if data.type == EnquiryType.PLANNER:
        company = db.scalar(
            select(PlannerCompany).where(func.lower(PlannerCompany.email) == data.email.lower())
        )
        if company is None:
            company = PlannerCompany(
                name=data.planner_company or data.client_name,
                contact_name=data.planner_contact_name,
                email=data.email.lower(),
                phone=data.phone,
            )
            db.add(company)
            db.flush()
        planner_id = company.id

    enquiry = Enquiry(
        type=data.type.value,
        pipeline_status=Pipeline.NEW_INQUIRY.value,
        region=region.value if region else None,
        timezone=TIMEZONES.get(region) if region else None,
        client_name=data.client_name.strip(),
        email=data.email.strip().lower(),
        phone=data.phone,
        preferred_contact=data.preferred_contact,
        wedding_date=data.wedding_date,
        venue_name=data.venue_name,
        venue_address=data.venue_address,
        wedding_type=data.wedding_type,
        bridal_package=data.bridal_package,
        attendant_hair_count=data.attendant_hair_count,
        attendant_makeup_count=data.attendant_makeup_count,
        trial_requested=data.trial_requested,
        travel_zone=suggest_travel_zone(region, data.venue_address, data.venue_name).value,
        travel_notes=data.travel_notes,
        notes=data.notes,
        services=data.services,
        planner_company_id=planner_id,
        raw_submission=data.raw or None,
        source_form=data.type.value,
        needs_review_flags=review_flags(region, data.wedding_date, today),
    )
    db.add(enquiry)
    db.flush()
    write_audit(
        db,
        actor,
        "enquiry.create",
        entity_type="enquiry",
        entity_id=enquiry.id,
        after={"type": enquiry.type, "region": enquiry.region, "flags": enquiry.needs_review_flags},
    )
    return enquiry


def find_duplicate(
    db: Session, email: str, wedding_date: date | None, since_days: int = 30, *, today: date
) -> Enquiry | None:
    if wedding_date is None:
        return None
    return db.scalar(
        select(Enquiry)
        .where(
            func.lower(Enquiry.email) == email.strip().lower(),
            Enquiry.wedding_date == wedding_date,
            Enquiry.created_at >= today - timedelta(days=since_days),
        )
        .order_by(Enquiry.created_at.desc())
        .limit(1)
    )


def search(
    db: Session,
    *,
    status: str | None = None,
    region: str | None = None,
    q: str | None = None,
    limit: int = 200,
) -> list[Enquiry]:
    stmt = select(Enquiry)
    if status:
        stmt = stmt.where(Enquiry.pipeline_status == status)
    if region:
        stmt = stmt.where(Enquiry.region == region)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Enquiry.client_name.ilike(like),
                Enquiry.email.ilike(like),
                Enquiry.venue_name.ilike(like),
            )
        )
    stmt = stmt.order_by(Enquiry.wedding_date.asc().nulls_last(), Enquiry.created_at.desc())
    return list(db.scalars(stmt.limit(limit)))
