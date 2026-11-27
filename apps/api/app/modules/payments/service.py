"""Venmo and Zelle payments are recorded by hand and count only once verified."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import utcnow
from app.modules.bookings import service as bookings
from app.modules.bookings.models import Booking, BookingStatus
from app.modules.documents.models import Invoice, InvoiceKind, InvoiceStatus
from app.modules.enquiries.models import Enquiry, Task
from app.modules.payments.models import Payment, PaymentMethod, PaymentStatus
from app.modules.platform.audit import Actor, write_audit


class PaymentError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def verified_total(db: Session, booking_id: Any, invoice_id: Any = None) -> int:
    q = select(func.coalesce(func.sum(Payment.amount_cents), 0)).where(
        Payment.booking_id == booking_id, Payment.status == PaymentStatus.VERIFIED
    )
    if invoice_id is not None:
        q = q.where(Payment.invoice_id == invoice_id)
    return int(db.scalar(q) or 0)


def _refresh(db: Session, b: Booking, e: Enquiry, actor: Actor) -> None:
    """Recompute invoice statuses and the deposit gate item from verified payments."""
    db.flush()
    paid = verified_total(db, b.id)
    for inv in db.scalars(
        select(Invoice).where(
            Invoice.booking_id == b.id,
            Invoice.status.in_([InvoiceStatus.ISSUED, InvoiceStatus.PAID]),
        )
    ):
        # Payments without an invoice count against the deposit first, then the balance.
        on_invoice = verified_total(db, b.id, inv.id)
        covered = on_invoice >= inv.amount_cents
        if inv.kind == InvoiceKind.DEPOSIT and not covered:
            covered = paid >= inv.amount_cents
        if inv.kind == InvoiceKind.BALANCE and not covered:
            covered = paid >= b.total_cents
        inv.status = InvoiceStatus.PAID if covered else InvoiceStatus.ISSUED

    deposit_ok = paid >= b.deposit_cents
    if deposit_ok and b.deposit_verified_at is None:
        b.deposit_verified_at = utcnow()
        bookings.try_book(db, b, e, actor)
    elif not deposit_ok and b.deposit_verified_at is not None:
        if b.status == BookingStatus.BOOKED:
            # Never un-book silently; a person decides what happens.
            db.add(
                Task(
                    entity_type="enquiry",
                    entity_id=e.id,
                    kind="deposit_reversed",
                    title=f"Deposit no longer covered for {e.client_name}: check payments",
                    due_at=utcnow(),
                )
            )
        else:
            b.deposit_verified_at = None


def record(
    db: Session,
    b: Booking,
    e: Enquiry,
    actor: Actor,
    *,
    method: PaymentMethod,
    amount_cents: int,
    received_on: date,
    invoice_id: Any = None,
    reference: str | None = None,
    note: str | None = None,
    verify: bool = False,
) -> Payment:
    if b.status == BookingStatus.CANCELLED:
        raise PaymentError("cancelled", "This booking is cancelled.")
    if amount_cents <= 0:
        raise PaymentError("bad_amount", "Enter an amount above zero.")
    if received_on > utcnow().date() + timedelta(days=1):
        raise PaymentError("future_date", "The payment date can't be in the future.")
    if invoice_id is not None:
        inv = db.get(Invoice, invoice_id)
        if inv is None or inv.booking_id != b.id:
            raise PaymentError("bad_invoice", "That invoice belongs to another booking.")
    p = Payment(
        booking_id=b.id,
        enquiry_id=e.id,
        invoice_id=invoice_id,
        method=method.value,
        amount_cents=amount_cents,
        received_on=received_on,
        reference=reference,
        note=note,
        status=PaymentStatus.RECORDED,
    )
    db.add(p)
    db.flush()
    write_audit(
        db,
        actor,
        "payment.record",
        entity_type="payment",
        entity_id=p.id,
        after={"amount_cents": amount_cents, "method": method.value, "reference": reference},
    )
    if verify:
        set_status(db, p, PaymentStatus.VERIFIED, actor)
    return p


ALLOWED = {
    PaymentStatus.RECORDED: {PaymentStatus.VERIFIED, PaymentStatus.REJECTED, PaymentStatus.VOID},
    PaymentStatus.VERIFIED: {PaymentStatus.VOID},
    PaymentStatus.REJECTED: {PaymentStatus.RECORDED},
    PaymentStatus.VOID: set(),
}


def set_status(
    db: Session, p: Payment, target: PaymentStatus, actor: Actor, reason: str | None = None
) -> None:
    current = PaymentStatus(p.status)
    if target not in ALLOWED[current]:
        raise PaymentError("not_allowed", f"A {current} payment can't become {target}.")
    needs_reason = target == PaymentStatus.REJECTED or (
        target == PaymentStatus.VOID and current == PaymentStatus.VERIFIED
    )
    if needs_reason and not (reason or "").strip():
        raise PaymentError("reason_required", "Say why, for the record.")
    p.status = target.value
    p.status_reason = reason
    p.verified_at = utcnow() if target == PaymentStatus.VERIFIED else p.verified_at
    write_audit(
        db,
        actor,
        f"payment.{target.value}",
        entity_type="payment",
        entity_id=p.id,
        before={"status": current.value},
        after={"status": target.value, "reason": reason},
    )
    b = db.get(Booking, p.booking_id)
    e = db.get(Enquiry, p.enquiry_id)
    assert b is not None and e is not None
    _refresh(db, b, e, actor)


def summary(db: Session, b: Booking) -> dict[str, int]:
    paid = verified_total(db, b.id)
    pending = int(
        db.scalar(
            select(func.coalesce(func.sum(Payment.amount_cents), 0)).where(
                Payment.booking_id == b.id, Payment.status == PaymentStatus.RECORDED
            )
        )
        or 0
    )
    return {
        "total_cents": b.total_cents,
        "paid_cents": paid,
        "awaiting_verification_cents": pending,
        "outstanding_cents": max(b.total_cents - paid, 0),
    }


def to_dict(db: Session, p: Payment) -> dict[str, Any]:
    e = db.get(Enquiry, p.enquiry_id)
    inv = db.get(Invoice, p.invoice_id) if p.invoice_id else None
    return {
        "id": p.id,
        "booking_id": p.booking_id,
        "enquiry_id": p.enquiry_id,
        "client_name": e.client_name if e else None,
        "invoice_id": p.invoice_id,
        "invoice_number": inv.number if inv else None,
        "method": p.method,
        "amount_cents": p.amount_cents,
        "received_on": p.received_on,
        "reference": p.reference,
        "note": p.note,
        "status": p.status,
        "status_reason": p.status_reason,
        "verified_at": p.verified_at,
        "created_at": p.created_at,
    }
