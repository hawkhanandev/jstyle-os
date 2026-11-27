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

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import utcnow
from app.modules.documents.models import Invoice, InvoiceStatus
from app.modules.email.models import EmailMessage, EmailThread
from app.modules.enquiries.models import CLOSED, Enquiry, Pipeline, Task
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


CHECKS: dict[str, Callable[[Session, ScheduledEmail, Enquiry, datetime], str | None]] = {
    "quote_follow_up": _check_quote_follow_up,
}


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
        s.outbox_event_id = outbox.enqueue(
            db,
            "email.send",
            f"scheduled:{s.id}",
            {"enquiry_id": str(s.enquiry_id), "template": s.template_key},
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
