from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import AwareDatetime, BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import get_session, utcnow
from app.modules.auth.deps import Account
from app.modules.bookings.models import Booking, BookingStatus
from app.modules.enquiries.models import Enquiry, Pipeline, Task
from app.modules.forms.models import FormSubmission
from app.modules.operations import service
from app.modules.operations.models import Trial, TrialStatus
from app.modules.payments.models import Payment, PaymentStatus
from app.modules.platform.models import OutboxEvent, OutboxStatus
from app.modules.quotes.models import Quote, QuoteStatus
from app.modules.replies.models import ReplySuggestion, SuggestionStatus

router = APIRouter(tags=["operations"])
DB = Annotated[Session, Depends(get_session)]


def _fail(exc: service.OpsError) -> HTTPException:
    code = 404 if exc.code in ("no_booking", "not_found") else 409
    return HTTPException(code, detail={"code": exc.code, "message": str(exc)})


def _load(db: Session, enquiry_id: uuid.UUID) -> tuple[Booking, Enquiry]:
    try:
        return service.booking_and_enquiry(db, enquiry_id)
    except service.OpsError as exc:
        raise _fail(exc) from exc


@router.get("/enquiries/{enquiry_id}/operations")
def get_ops(enquiry_id: uuid.UUID, account: Account, db: DB) -> dict[str, Any]:
    b, e = _load(db, enquiry_id)
    data = service.ops_dict(db, b, e)
    db.commit()  # plan_for may have created the empty plan
    return data


class TimelineRow(BaseModel):
    time: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    person: str = Field(min_length=1, max_length=100)
    service: str = Field(default="", max_length=100)
    stylist: str = Field(default="", max_length=100)


class PlanIn(BaseModel):
    getting_ready_address: str | None = Field(default=None, max_length=500)
    timeline: list[TimelineRow] = Field(default_factory=list, max_length=60)
    notes: str | None = Field(default=None, max_length=4000)


@router.put("/enquiries/{enquiry_id}/plan")
def put_plan(enquiry_id: uuid.UUID, body: PlanIn, account: Account, db: DB) -> dict[str, Any]:
    b, e = _load(db, enquiry_id)
    service.save_plan(
        db,
        b,
        account.actor,
        getting_ready_address=body.getting_ready_address,
        timeline=[r.model_dump() for r in body.timeline],
        notes=body.notes,
    )
    db.commit()
    return service.ops_dict(db, b, e)


class TrialIn(BaseModel):
    starts_at: AwareDatetime
    location: str | None = Field(default=None, max_length=300)
    status: TrialStatus = TrialStatus.SCHEDULED
    notes: str | None = Field(default=None, max_length=2000)


@router.post("/enquiries/{enquiry_id}/trials", status_code=201)
def add_trial(enquiry_id: uuid.UUID, body: TrialIn, account: Account, db: DB) -> dict[str, Any]:
    b, e = _load(db, enquiry_id)
    try:
        service.save_trial(db, b, e, account.actor, trial_id=None, **body.model_dump())
    except service.OpsError as exc:
        db.rollback()
        raise _fail(exc) from exc
    db.commit()
    return service.ops_dict(db, b, e)


@router.put("/enquiries/{enquiry_id}/trials/{trial_id}")
def update_trial(
    enquiry_id: uuid.UUID, trial_id: uuid.UUID, body: TrialIn, account: Account, db: DB
) -> dict[str, Any]:
    b, e = _load(db, enquiry_id)
    try:
        service.save_trial(db, b, e, account.actor, trial_id=trial_id, **body.model_dump())
    except service.OpsError as exc:
        db.rollback()
        raise _fail(exc) from exc
    db.commit()
    return service.ops_dict(db, b, e)


@router.post("/enquiries/{enquiry_id}/final-timeline/send", status_code=202)
def send_timeline(enquiry_id: uuid.UUID, account: Account, db: DB) -> dict[str, Any]:
    b, e = _load(db, enquiry_id)
    try:
        service.send_final_timeline_now(db, b, e, account.actor)
    except service.OpsError as exc:
        db.rollback()
        raise _fail(exc) from exc
    db.commit()
    return service.ops_dict(db, b, e)


@router.get("/calendar")
def calendar(account: Account, db: DB, start: date, end: date) -> list[dict[str, Any]]:
    if end < start or (end - start).days > 400:
        raise HTTPException(422, detail={"code": "bad_range", "message": "Invalid range."})
    events: list[dict[str, Any]] = []
    rows = db.execute(
        select(Enquiry, Booking)
        .join(Booking, Booking.enquiry_id == Enquiry.id)
        .where(
            Enquiry.wedding_date >= start,
            Enquiry.wedding_date <= end,
            Booking.status != BookingStatus.CANCELLED,
        )
    ).all()
    for e, b in rows:
        events.append(
            {
                "type": "wedding",
                "date": e.wedding_date,
                "at": None,
                "title": e.client_name,
                "enquiry_id": e.id,
                "status": b.status,
                "detail": e.venue_name,
                "timezone": e.timezone,
            }
        )
    lo = datetime.combine(start, time.min, tzinfo=UTC) - timedelta(days=1)
    hi = datetime.combine(end, time.max, tzinfo=UTC) + timedelta(days=1)
    for t, e in db.execute(
        select(Trial, Enquiry)
        .join(Enquiry, Enquiry.id == Trial.enquiry_id)
        .where(Trial.starts_at >= lo, Trial.starts_at <= hi, Trial.status != "cancelled")
    ).all():
        events.append(
            {
                "type": "trial",
                "date": None,
                "at": t.starts_at,
                "title": f"Trial: {e.client_name}",
                "enquiry_id": e.id,
                "status": t.status,
                "detail": t.location,
                "timezone": e.timezone,
            }
        )
    return events


def _count(db: Session, q: Any) -> int:
    return int(db.scalar(select(func.count()).select_from(q.subquery())) or 0)


@router.get("/dashboard")
def dashboard(account: Account, db: DB) -> dict[str, Any]:
    today = utcnow().date()
    outstanding = 0
    for b in db.scalars(select(Booking).where(Booking.status == BookingStatus.BOOKED)):
        outstanding += service.outstanding(db, b)
    upcoming = db.execute(
        select(Enquiry.id, Enquiry.client_name, Enquiry.wedding_date, Enquiry.venue_name)
        .join(Booking, Booking.enquiry_id == Enquiry.id)
        .where(Booking.status == BookingStatus.BOOKED, Enquiry.wedding_date >= today)
        .order_by(Enquiry.wedding_date)
        .limit(8)
    ).all()
    tasks = db.scalars(
        select(Task).where(Task.status == "open").order_by(Task.due_at.nulls_last()).limit(10)
    ).all()
    return {
        "counts": {
            "new_enquiries": _count(
                db, select(Enquiry.id).where(Enquiry.pipeline_status == Pipeline.NEW_INQUIRY)
            ),
            "quotes_awaiting_approval": _count(
                db, select(Quote.id).where(Quote.status == QuoteStatus.AWAITING_APPROVAL)
            ),
            "quotes_sent": _count(db, select(Quote.id).where(Quote.status == QuoteStatus.SENT)),
            "replies_to_review": _count(
                db,
                select(ReplySuggestion.id).where(
                    ReplySuggestion.status == SuggestionStatus.PENDING
                ),
            ),
            "awaiting_signed_contract": _count(
                db,
                select(Enquiry.id).where(
                    Enquiry.pipeline_status == Pipeline.CONTRACT_DEPOSIT_PENDING
                ),
            ),
            "payments_to_verify": _count(
                db, select(Payment.id).where(Payment.status == PaymentStatus.RECORDED)
            ),
            "outstanding_balances_cents": outstanding,
            "held_submissions": _count(
                db, select(FormSubmission.id).where(FormSubmission.status == "held")
            ),
            "failed_automations": _count(
                db,
                select(OutboxEvent.id).where(
                    OutboxEvent.status.in_([OutboxStatus.FAILED, OutboxStatus.DEAD])
                ),
            ),
        },
        "upcoming_weddings": [
            {
                "enquiry_id": r.id,
                "client_name": r.client_name,
                "date": r.wedding_date,
                "venue": r.venue_name,
            }
            for r in upcoming
        ],
        "open_tasks": [
            {
                "id": t.id,
                "title": t.title,
                "kind": t.kind,
                "entity_type": t.entity_type,
                "entity_id": t.entity_id,
                "due_at": t.due_at,
            }
            for t in tasks
        ],
    }


@router.post("/tasks/{task_id}/done", status_code=204)
def task_done(task_id: uuid.UUID, account: Account, db: DB) -> None:
    t = db.get(Task, task_id)
    if t is None:
        raise HTTPException(404, detail={"code": "not_found", "message": "Task not found."})
    t.status = "done"
    t.completed_at = utcnow()
    db.commit()
