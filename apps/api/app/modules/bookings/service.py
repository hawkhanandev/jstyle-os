"""Accepting a quote, and the confirmation gate that guards BOOKED."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import utcnow
from app.modules.bookings.models import Booking, BookingStatus
from app.modules.enquiries.models import Enquiry, Pipeline
from app.modules.enquiries.pipeline import transition
from app.modules.platform import outbox
from app.modules.platform.audit import Actor, write_audit
from app.modules.quotes import service as quotes
from app.modules.quotes.models import Quote, QuoteStatus
from app.modules.scheduling import service as scheduling

GATE_LABELS = {
    "quote_accepted": "Quote accepted",
    "contract_signed": "Contract marked as signed",
    "deposit_verified": "Deposit received and verified",
    "stylists_required": "Number of stylists set",
}


class BookingError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def for_enquiry(db: Session, enquiry_id: uuid.UUID) -> Booking | None:
    return db.scalar(select(Booking).where(Booking.enquiry_id == enquiry_id))


def accept_quote(
    db: Session,
    q: Quote,
    e: Enquiry,
    actor: Actor,
    *,
    via: str,
    message_id: uuid.UUID | None = None,
) -> Booking:
    """Record the client's acceptance. Always a staff action (a click or a confirmed reply)."""
    if q.status != QuoteStatus.SENT:
        raise BookingError("not_sent", "Only the quote the client has received can be accepted.")
    if quotes.open_quote(db, e.id) is not None:
        raise BookingError(
            "revision_open", "A revised quote is in progress. Withdraw it before accepting."
        )
    if for_enquiry(db, e.id) is not None:
        raise BookingError("already_accepted", "This enquiry already has a booking.")
    q.status = QuoteStatus.ACCEPTED
    transition(db, e, Pipeline.QUOTE_ACCEPTED, actor)
    scheduling.cancel(db, e.id, kinds={"quote_follow_up"}, reason="quote accepted")
    b = Booking(
        enquiry_id=e.id,
        quote_id=q.id,
        status=BookingStatus.PENDING,
        accepted_at=utcnow(),
        accepted_via=via,
        accepted_message_id=message_id,
        total_cents=q.total_cents,
        deposit_cents=q.deposit_cents,
        balance_cents=q.balance_cents,
        stylists_required=q.stylists_required or e.stylists_required,
    )
    db.add(b)
    db.flush()
    write_audit(
        db,
        actor,
        "quote.accept",
        entity_type="quote",
        entity_id=q.id,
        after={"via": via, "booking_id": str(b.id), "total_cents": q.total_cents},
    )
    return b


def gate(db: Session, b: Booking) -> list[str]:
    """What still stands between this booking and BOOKED. Empty means clear."""
    missing: list[str] = []
    q = db.get(Quote, b.quote_id)
    if q is None or q.status != QuoteStatus.ACCEPTED:
        missing.append("quote_accepted")
    if b.contract_signed_at is None:
        missing.append("contract_signed")
    if b.deposit_verified_at is None:
        missing.append("deposit_verified")
    if not b.stylists_required:
        missing.append("stylists_required")
    return missing


def try_book(db: Session, b: Booking, e: Enquiry, actor: Actor) -> list[str]:
    """Move to BOOKED if the gate is clear. Called after every change to a gate item."""
    if b.status != BookingStatus.PENDING:
        return []
    missing = gate(db, b)
    if missing or Pipeline(e.pipeline_status) != Pipeline.CONTRACT_DEPOSIT_PENDING:
        return missing or ["contract_and_invoice_sent"]
    transition(db, e, Pipeline.BOOKED, actor, missing=missing)
    b.status = BookingStatus.BOOKED
    b.booked_at = utcnow()
    write_audit(db, actor, "booking.booked", entity_type="booking", entity_id=b.id)
    outbox.enqueue(
        db,
        "email.send",
        f"booking_confirmed:{b.id}",
        {"enquiry_id": str(e.id), "template": "booking_confirmed"},
        aggregate_type="booking",
        aggregate_id=b.id,
    )
    return []


def set_stylists(db: Session, b: Booking, e: Enquiry, n: int, actor: Actor) -> None:
    before = b.stylists_required
    b.stylists_required = n
    write_audit(
        db,
        actor,
        "booking.stylists",
        entity_type="booking",
        entity_id=b.id,
        before={"stylists_required": before},
        after={"stylists_required": n},
    )
    try_book(db, b, e, actor)


def to_dict(db: Session, b: Booking, e: Enquiry) -> dict[str, Any]:
    missing = gate(db, b)
    q = db.get(Quote, b.quote_id)
    items = [
        {"key": k, "label": label, "done": k not in missing} for k, label in GATE_LABELS.items()
    ]
    items.insert(
        2,
        {
            "key": "contract_and_invoice_sent",
            "label": "Contract and deposit invoice sent",
            "done": Pipeline(e.pipeline_status)
            in (Pipeline.CONTRACT_DEPOSIT_PENDING, Pipeline.BOOKED),
        },
    )
    return {
        "id": b.id,
        "enquiry_id": b.enquiry_id,
        "quote_id": b.quote_id,
        "quote_version": q.version if q else None,
        "status": b.status,
        "accepted_at": b.accepted_at,
        "accepted_via": b.accepted_via,
        "total_cents": b.total_cents,
        "deposit_cents": b.deposit_cents,
        "balance_cents": b.balance_cents,
        "stylists_required": b.stylists_required,
        "contract_signed_at": b.contract_signed_at,
        "deposit_verified_at": b.deposit_verified_at,
        "booked_at": b.booked_at,
        "checklist": items,
        "missing": missing,
    }
