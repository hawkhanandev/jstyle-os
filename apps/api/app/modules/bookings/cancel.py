"""Cancelling a wedding after acceptance: stops every pending email and voids unpaid paperwork."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import utcnow
from app.modules.bookings.models import Booking, BookingStatus
from app.modules.documents.models import Contract, ContractStatus, Invoice, InvoiceStatus
from app.modules.enquiries.models import Enquiry, Pipeline
from app.modules.enquiries.pipeline import transition
from app.modules.google.events import calendar_changed
from app.modules.platform.audit import Actor, write_audit
from app.modules.platform.models import OutboxEvent, OutboxStatus
from app.modules.scheduling import service as scheduling

CANCELLABLE = {Pipeline.QUOTE_ACCEPTED, Pipeline.CONTRACT_DEPOSIT_PENDING, Pipeline.BOOKED}


class CancelError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def cancel_wedding(db: Session, e: Enquiry, reason: str, actor: Actor) -> dict[str, int]:
    if Pipeline(e.pipeline_status) not in CANCELLABLE:
        raise CancelError("wrong_stage", "Only accepted or booked weddings can be cancelled.")
    if not reason.strip():
        raise CancelError("reason_required", "Say why the wedding was cancelled.")
    transition(db, e, Pipeline.CANCELLED, actor, reason=reason)

    b = db.scalar(select(Booking).where(Booking.enquiry_id == e.id))
    voided = 0
    if b is not None:
        b.status = BookingStatus.CANCELLED
        b.cancelled_at = utcnow()
        b.cancel_reason = reason
        for inv in db.scalars(
            select(Invoice).where(
                Invoice.booking_id == b.id,
                Invoice.status.in_([InvoiceStatus.PREPARED, InvoiceStatus.ISSUED]),
            )
        ):
            inv.status = InvoiceStatus.VOID
            voided += 1
        for c in db.scalars(
            select(Contract).where(
                Contract.booking_id == b.id,
                Contract.status.in_([ContractStatus.PREPARED, ContractStatus.SENDING]),
            )
        ):
            c.status = ContractStatus.VOID

    scheduled = scheduling.cancel(db, e.id, reason="wedding cancelled")
    calendar_changed(db, e.id)
    # Emails already queued but not yet sent are stopped too.
    stopped = 0
    for ev in db.scalars(
        select(OutboxEvent).where(
            OutboxEvent.status.in_([OutboxStatus.PENDING, OutboxStatus.PAUSED]),
            OutboxEvent.kind.in_(["email.send", "booking.send_contract", "email.reply"]),
            OutboxEvent.payload["enquiry_id"].astext == str(e.id),
        )
    ):
        ev.status = OutboxStatus.DEAD
        ev.last_error = "cancelled with the wedding"
        stopped += 1
    write_audit(
        db,
        actor,
        "wedding.cancel",
        entity_type="enquiry",
        entity_id=e.id,
        after={
            "reason": reason,
            "invoices_voided": voided,
            "scheduled_cancelled": scheduled,
            "queued_stopped": stopped,
        },
    )
    return {"invoices_voided": voided, "scheduled_cancelled": scheduled, "queued_stopped": stopped}
