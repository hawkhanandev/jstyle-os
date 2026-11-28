"""Scheduled emails and daily checks.

Every scheduled email is re-checked when it comes due: if the situation changed
(client replied, enquiry closed, quote replaced) it is skipped, not sent.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import utcnow
from app.modules.bookings.models import Booking, BookingStatus
from app.modules.documents.models import Invoice, InvoiceStatus
from app.modules.email.models import EmailMessage, EmailThread
from app.modules.enquiries.models import CLOSED, Enquiry, Pipeline, Task
from app.modules.operations.models import Trial, TrialStatus, WeddingPlan
from app.modules.payments.models import Payment, PaymentStatus
from app.modules.platform import outbox, settings
from app.modules.platform.audit import Actor, write_audit
from app.modules.quotes.models import Quote, QuoteStatus
from app.modules.scheduling.models import ScheduledEmail, ScheduledStatus

SEND_HOUR = time(10, 0)  # local time of the wedding's region
DEFAULT_TZ = "Pacific/Honolulu"


def local_at(day: date, tz: str | None, at: time = SEND_HOUR) -> datetime:
    """`day` at `at` in the enquiry's time zone, as an aware UTC datetime."""
    local = datetime.combine(day, at, tzinfo=ZoneInfo(tz or DEFAULT_TZ))
    return local.astimezone(ZoneInfo("UTC"))


def schedule(
    db: Session,
    e: Enquiry,
    kind: str,
    template_key: str,
    send_at: datetime,
    *,
    ref_id: uuid.UUID | None = None,
    note: str | None = None,
) -> ScheduledEmail:
    """Replace any pending email of the same kind for this enquiry."""
    cancel(db, e.id, kinds={kind}, reason="rescheduled")
    s = ScheduledEmail(
        enquiry_id=e.id,
        kind=kind,
        template_key=template_key,
        send_at=send_at,
        status=ScheduledStatus.SCHEDULED,
        ref_id=ref_id,
        note=note,
    )
    db.add(s)
    db.flush()
    return s


def cancel(
    db: Session, enquiry_id: uuid.UUID, *, kinds: set[str] | None = None, reason: str
) -> int:
    q = select(ScheduledEmail).where(
        ScheduledEmail.enquiry_id == enquiry_id,
        ScheduledEmail.status == ScheduledStatus.SCHEDULED,
    )
    if kinds:
        q = q.where(ScheduledEmail.kind.in_(kinds))
    n = 0
    for s in db.scalars(q):
        s.status = ScheduledStatus.CANCELLED
        s.note = reason
        n += 1
    return n


# --- Rules -----------------------------------------------------------------


def schedule_quote_follow_up(db: Session, q: Quote, e: Enquiry) -> ScheduledEmail:
    days = int(settings.get(db, "quote_follow_up_days") or 5)
    sent_day = (q.sent_at or utcnow()).astimezone(ZoneInfo(e.timezone or DEFAULT_TZ)).date()
    return schedule(
        db,
        e,
        "quote_follow_up",
        "quote_follow_up",
        local_at(sent_day + timedelta(days=days), e.timezone),
        ref_id=q.id,
    )


def _client_replied_since(db: Session, e: Enquiry, since: datetime) -> bool:
    return (
        db.scalar(
            select(EmailMessage.id)
            .join(EmailThread, EmailThread.id == EmailMessage.thread_id)
            .where(
                EmailThread.enquiry_id == e.id,
                EmailMessage.direction == "inbound",
                EmailMessage.sent_at > since,
            )
            .limit(1)
        )
        is not None
    )


def _check_quote_follow_up(db: Session, s: ScheduledEmail, e: Enquiry, now: datetime) -> str | None:
    q = db.get(Quote, s.ref_id) if s.ref_id else None
    if q is None or q.status != QuoteStatus.SENT:
        return "quote is no longer the one with the client"
    if Pipeline(e.pipeline_status) != Pipeline.QUOTE_SENT:
        return f"enquiry is {e.pipeline_status}"
    if e.follow_ups_paused_until and e.follow_ups_paused_until > now:
        return "follow-ups paused"
    if q.sent_at and _client_replied_since(db, e, q.sent_at):
        return "client replied"
    return None


def _booking(db: Session, s: ScheduledEmail) -> Booking | None:
    return db.scalar(select(Booking).where(Booking.enquiry_id == s.enquiry_id))


def _outstanding(db: Session, b: Booking) -> int:
    paid = db.scalar(
        select(func.coalesce(func.sum(Payment.amount_cents), 0)).where(
            Payment.booking_id == b.id, Payment.status == PaymentStatus.VERIFIED
        )
    )
    return max(b.total_cents - int(paid or 0), 0)


def _task(db: Session, e: Enquiry, kind: str, title: str) -> None:
    db.add(Task(entity_type="enquiry", entity_id=e.id, kind=kind, title=title, due_at=utcnow()))


def _check_booked(db: Session, s: ScheduledEmail, e: Enquiry, now: datetime) -> str | None:
    b = _booking(db, s)
    if b is None or b.status != BookingStatus.BOOKED:
        return "booking isn't confirmed"
    return None


def _check_balance(db: Session, s: ScheduledEmail, e: Enquiry, now: datetime) -> str | None:
    b = _booking(db, s)
    if b is None or b.status != BookingStatus.BOOKED:
        return "booking isn't confirmed"
    if _outstanding(db, b) == 0:
        return "balance already paid"
    return None


def _check_final_timeline(db: Session, s: ScheduledEmail, e: Enquiry, now: datetime) -> str | None:
    b = _booking(db, s)
    if b is None or b.status != BookingStatus.BOOKED:
        return "booking isn't confirmed"
    plan = db.scalar(select(WeddingPlan).where(WeddingPlan.booking_id == b.id))
    if plan is not None and plan.final_timeline_sent_at is not None:
        return "already sent"
    if _outstanding(db, b) > 0:
        _task(
            db,
            e,
            "final_timeline_blocked",
            f"Final timeline for {e.client_name} waits on the balance",
        )
        return "balance not paid in full"
    if plan is None or not plan.timeline:
        _task(db, e, "final_timeline_blocked", f"Add the day-of timeline for {e.client_name}")
        return "no timeline entered"
    return None


def _check_trial(db: Session, s: ScheduledEmail, e: Enquiry, now: datetime) -> str | None:
    t = db.get(Trial, s.ref_id) if s.ref_id else None
    if t is None or t.status != TrialStatus.SCHEDULED:
        return "trial no longer scheduled"
    if t.starts_at < now:
        return "trial already happened"
    return None


CHECKS: dict[str, Callable[[Session, ScheduledEmail, Enquiry, datetime], str | None]] = {
    "quote_follow_up": _check_quote_follow_up,
    "prep_guide": _check_booked,
    "balance_reminder": _check_balance,
    "final_timeline": _check_final_timeline,
    "thank_you_review": _check_booked,
    "trial_reminder": _check_trial,
}

# Kinds that carry a generated PDF go through the document handler.
DOCUMENT_KINDS = {
    "prep_guide": "prep_guide",
    "balance_reminder": "balance_invoice",
    "final_timeline": "final_timeline",
}


def _context(db: Session, s: ScheduledEmail, e: Enquiry) -> dict[str, Any]:
    if s.kind == "trial_reminder" and s.ref_id:
        t = db.get(Trial, s.ref_id)
        if t is not None:
            local = t.starts_at.astimezone(ZoneInfo(e.timezone or DEFAULT_TZ))
            when = f"{local:%A, %B} {local.day} at {local:%-I:%M %p}"
            return {"trial_date": when, "trial_location": t.location or ""}
    return {}


# --- Dispatcher ------------------------------------------------------------


def dispatch_due(db: Session, now: datetime | None = None, limit: int = 50) -> list[str]:
    """Queue due emails whose conditions still hold; skip the rest. Caller commits."""
    now = now or utcnow()
    rows = db.scalars(
        select(ScheduledEmail)
        .where(ScheduledEmail.status == ScheduledStatus.SCHEDULED, ScheduledEmail.send_at <= now)
        .order_by(ScheduledEmail.send_at)
        .limit(limit)
        .with_for_update(skip_locked=True)
    ).all()
    results = []
    for s in rows:
        e = db.get(Enquiry, s.enquiry_id)
        reason: str | None
        if e is None:
            reason = "enquiry missing"
        elif Pipeline(e.pipeline_status) in CLOSED:
            reason = f"enquiry is {e.pipeline_status}"
        else:
            check = CHECKS.get(s.kind)
            reason = check(db, s, e, now) if check else None
        if reason:
            s.status = ScheduledStatus.SKIPPED
            s.note = reason
            results.append("skipped")
            continue
        payload: dict[str, Any] = {"enquiry_id": str(s.enquiry_id), "template": s.template_key}
        kind = "email.send"
        if s.kind in DOCUMENT_KINDS:
            kind = "booking.document_email"
            payload["doc"] = DOCUMENT_KINDS[s.kind]
        elif e is not None:
            payload["context"] = _context(db, s, e)
        s.outbox_event_id = outbox.enqueue(
            db,
            kind,
            f"scheduled:{s.id}",
            payload,
            aggregate_type="scheduled_email",
            aggregate_id=s.id,
        )
        s.status = ScheduledStatus.QUEUED
        results.append("queued")
    return results


def daily_checks(db: Session, today: date | None = None) -> int:
    """Raise one task per overdue deposit invoice. Idempotent."""
    today = today or utcnow().date()
    created = 0
    for inv in db.scalars(
        select(Invoice).where(Invoice.status == InvoiceStatus.ISSUED, Invoice.due_on < today)
    ):
        exists = db.scalar(
            select(Task.id).where(
                Task.kind == f"{inv.kind}_overdue",
                Task.entity_type == "invoice",
                Task.entity_id == inv.id,
            )
        )
        if exists:
            continue
        e = db.get(Enquiry, inv.enquiry_id)
        db.add(
            Task(
                entity_type="invoice",
                entity_id=inv.id,
                kind=f"{inv.kind}_overdue",
                title=f"{inv.kind.capitalize()} {inv.number} overdue"
                + (f" for {e.client_name}" if e else ""),
                due_at=utcnow(),
            )
        )
        created += 1
    db.flush()
    return created


def to_dict(s: ScheduledEmail) -> dict[str, Any]:
    return {
        "id": s.id,
        "enquiry_id": s.enquiry_id,
        "kind": s.kind,
        "template_key": s.template_key,
        "send_at": s.send_at,
        "status": s.status,
        "note": s.note,
    }


def audit_cancel(db: Session, actor: Actor, e: Enquiry, n: int, reason: str) -> None:
    write_audit(
        db,
        actor,
        "scheduled_email.cancel",
        entity_type="enquiry",
        entity_id=e.id,
        after={"cancelled": n, "reason": reason},
    )
