"""Wedding operations after BOOKED: trials, the day-of plan and the booking emails."""

from __future__ import annotations

import uuid
from datetime import datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import utcnow
from app.modules.bookings.models import Booking, BookingStatus
from app.modules.enquiries.models import Enquiry
from app.modules.operations.models import Trial, TrialStatus, WeddingPlan
from app.modules.payments.models import Payment, PaymentStatus
from app.modules.platform import outbox
from app.modules.platform.audit import Actor, write_audit
from app.modules.scheduling import service as scheduling
from app.modules.scheduling.service import DEFAULT_TZ, local_at

BOOKING_KINDS = {"prep_guide", "balance_reminder", "final_timeline", "thank_you_review"}


class OpsError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def outstanding(db: Session, b: Booking) -> int:
    paid = db.scalar(
        select(func.coalesce(func.sum(Payment.amount_cents), 0)).where(
            Payment.booking_id == b.id, Payment.status == PaymentStatus.VERIFIED
        )
    )
    return max(b.total_cents - int(paid or 0), 0)


def plan_for(db: Session, b: Booking) -> WeddingPlan:
    p = db.scalar(select(WeddingPlan).where(WeddingPlan.booking_id == b.id))
    if p is None:
        p = WeddingPlan(booking_id=b.id, timeline=[])
        db.add(p)
        db.flush()
    return p


def schedule_booking_emails(
    db: Session, b: Booking, e: Enquiry, now: datetime | None = None
) -> int:
    """(Re)schedule every booking email from the wedding date. Safe to call repeatedly."""
    now = now or utcnow()
    scheduling.cancel(db, e.id, kinds=BOOKING_KINDS, reason="rescheduled")
    if e.wedding_date is None or b.status != BookingStatus.BOOKED:
        return 0
    tz = e.timezone
    day = e.wedding_date
    plan: list[tuple[str, datetime, bool]] = [
        # kind, when, send now if that moment has already passed ("last-minute")
        ("prep_guide", local_at(day - timedelta(days=14), tz), True),
        ("balance_reminder", local_at(day - timedelta(days=5), tz), True),
        ("final_timeline", local_at(day - timedelta(days=2), tz, time(12, 0)), False),
        ("thank_you_review", local_at(day + timedelta(days=2), tz), False),
    ]
    wedding_start = local_at(day, tz, time(0, 0))
    n = 0
    for kind, when, catch_up in plan:
        if when < now:
            if not catch_up or now >= wedding_start:
                continue
            when = now
        scheduling.schedule(db, e, kind, kind, when, ref_id=b.id)
        n += 1
    return n


def schedule_trial_reminder(db: Session, t: Trial, e: Enquiry) -> None:
    scheduling.cancel(db, e.id, kinds={"trial_reminder"}, reason="trial changed")
    if t.status != TrialStatus.SCHEDULED:
        return
    tz = e.timezone or DEFAULT_TZ
    local_day = t.starts_at.astimezone(ZoneInfo(tz)).date()
    when = local_at(local_day - timedelta(days=2), tz)
    if when > utcnow():
        scheduling.schedule(db, e, "trial_reminder", "trial_reminder", when, ref_id=t.id)


def booking_and_enquiry(db: Session, enquiry_id: uuid.UUID) -> tuple[Booking, Enquiry]:
    e = db.get(Enquiry, enquiry_id)
    b = db.scalar(select(Booking).where(Booking.enquiry_id == enquiry_id)) if e else None
    if e is None or b is None:
        raise OpsError("no_booking", "No booking yet.")
    return b, e


def save_trial(
    db: Session,
    b: Booking,
    e: Enquiry,
    actor: Actor,
    *,
    trial_id: uuid.UUID | None,
    starts_at: datetime,
    location: str | None,
    status: TrialStatus,
    notes: str | None,
) -> Trial:
    if b.status == BookingStatus.CANCELLED:
        raise OpsError("cancelled", "This wedding is cancelled.")
    if trial_id:
        t = db.get(Trial, trial_id)
        if t is None or t.booking_id != b.id:
            raise OpsError("not_found", "Trial not found.")
    else:
        t = Trial(booking_id=b.id, enquiry_id=e.id)
        db.add(t)
    t.starts_at, t.location, t.status, t.notes = starts_at, location, status.value, notes
    db.flush()
    schedule_trial_reminder(db, t, e)
    write_audit(
        db,
        actor,
        "trial.save",
        entity_type="trial",
        entity_id=t.id,
        after={"starts_at": starts_at.isoformat(), "status": status.value},
    )
    return t


def save_plan(
    db: Session,
    b: Booking,
    actor: Actor,
    *,
    getting_ready_address: str | None,
    timeline: list[dict[str, str]],
    notes: str | None,
) -> WeddingPlan:
    p = plan_for(db, b)
    p.getting_ready_address = getting_ready_address
    p.timeline = sorted(timeline, key=lambda r: r.get("time", ""))
    p.notes = notes
    write_audit(
        db, actor, "plan.save", entity_type="booking", entity_id=b.id, after={"rows": len(timeline)}
    )
    return p


def final_timeline_blockers(db: Session, b: Booking) -> list[str]:
    blockers = []
    if b.status != BookingStatus.BOOKED:
        blockers.append("Booking isn't confirmed")
    if outstanding(db, b) > 0:
        blockers.append("Balance not paid in full")
    if not plan_for(db, b).timeline:
        blockers.append("No timeline entered")
    return blockers


def send_final_timeline_now(db: Session, b: Booking, e: Enquiry, actor: Actor) -> None:
    blockers = final_timeline_blockers(db, b)
    if blockers:
        raise OpsError("blocked", "Can't send yet: " + "; ".join(blockers) + ".")
    scheduling.cancel(db, e.id, kinds={"final_timeline"}, reason="sent by hand")
    outbox.enqueue(
        db,
        "booking.document_email",
        f"final_timeline:{b.id}:{uuid.uuid4()}",
        {"enquiry_id": str(e.id), "template": "final_timeline", "doc": "final_timeline"},
        aggregate_type="booking",
        aggregate_id=b.id,
    )
    write_audit(db, actor, "final_timeline.send", entity_type="booking", entity_id=b.id)


def trial_dict(t: Trial) -> dict[str, Any]:
    return {
        "id": t.id,
        "starts_at": t.starts_at,
        "location": t.location,
        "status": t.status,
        "notes": t.notes,
    }


def ops_dict(db: Session, b: Booking, e: Enquiry) -> dict[str, Any]:
    p = plan_for(db, b)
    trials = db.scalars(select(Trial).where(Trial.booking_id == b.id).order_by(Trial.starts_at))
    return {
        "booking_status": b.status,
        "timezone": e.timezone or DEFAULT_TZ,
        "outstanding_cents": outstanding(db, b),
        "plan": {
            "getting_ready_address": p.getting_ready_address,
            "timeline": p.timeline,
            "notes": p.notes,
            "final_timeline_sent_at": p.final_timeline_sent_at,
        },
        "final_timeline_blockers": final_timeline_blockers(db, b),
        "trials": [trial_dict(t) for t in trials],
    }
