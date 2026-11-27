"""Contracts and invoices: prepare the PDFs, send them together, mark the contract signed."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.db import utcnow
from app.modules.bookings import service as bookings
from app.modules.bookings.models import Booking, BookingStatus
from app.modules.documents import pdf, storage
from app.modules.documents.models import (
    Contract,
    ContractStatus,
    Document,
    Invoice,
    InvoiceCounter,
    InvoiceKind,
    InvoiceStatus,
)
from app.modules.email.send import REGION_NAMES, long_date
from app.modules.enquiries.models import Enquiry, Pipeline, PlannerCompany
from app.modules.enquiries.pipeline import transition
from app.modules.platform import outbox, settings
from app.modules.platform.audit import Actor, write_audit
from app.modules.quotes.models import QuoteLineItem
from app.modules.quotes.service import money

SIGNED_METHODS = {"paper": "Signed on paper", "pdf": "Signed PDF returned", "other": "Other"}


class DocumentError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def next_invoice_number(db: Session, year: int) -> str:
    db.execute(
        insert(InvoiceCounter)
        .values(year=year, last=0)
        .on_conflict_do_nothing(index_elements=["year"])
    )
    counter = db.get(InvoiceCounter, year, with_for_update=True)
    assert counter is not None
    counter.last += 1
    db.flush()
    return f"JS-{year}-{counter.last:04d}"


def _business(db: Session) -> dict[str, Any]:
    b = dict(settings.get(db, "business"))
    b["address_lines"] = [x.strip() for x in str(b.get("address", "")).splitlines() if x.strip()]
    b.setdefault("logo_data_uri", "")
    return b


def _context(db: Session, b: Booking, e: Enquiry) -> dict[str, Any]:
    lines = db.scalars(
        select(QuoteLineItem)
        .where(QuoteLineItem.quote_id == b.quote_id)
        .order_by(QuoteLineItem.sort)
    )
    hours = int(settings.get(db, "balance_due_hours") or 48)
    return {
        "business": _business(db),
        "payment": settings.get(db, "payment_instructions"),
        "client": {
            "name": e.client_name,
            "email": e.email,
            "phone": e.phone,
            "planner": _planner_name(db, e),
        },
        "wedding": {
            "date": long_date(e.wedding_date),
            "venue": e.venue_name or "",
            "address": e.venue_address or "",
            "region": REGION_NAMES.get(e.region or "", ""),
        },
        "lines": [
            {
                "description": li.description,
                "quantity": li.quantity,
                "amount": money(li.amount_cents),
            }
            for li in lines
        ],
        "totals": {
            "total": money(b.total_cents),
            "deposit": money(b.deposit_cents),
            "balance": money(b.balance_cents),
        },
        "balance_due": f"{hours} hours before the wedding",
    }


def _planner_name(db: Session, e: Enquiry) -> str | None:
    if e.planner_company_id is None:
        return None
    pc = db.get(PlannerCompany, e.planner_company_id)
    return pc.name if pc else None


def _active_contract(db: Session, b: Booking) -> Contract | None:
    return db.scalar(
        select(Contract)
        .where(Contract.booking_id == b.id, Contract.status != ContractStatus.VOID)
        .order_by(Contract.version.desc())
        .limit(1)
    )


def _active_deposit(db: Session, b: Booking) -> Invoice | None:
    return db.scalar(
        select(Invoice).where(
            Invoice.booking_id == b.id,
            Invoice.kind == InvoiceKind.DEPOSIT,
            Invoice.status != InvoiceStatus.VOID,
        )
    )


def prepare(db: Session, b: Booking, e: Enquiry, actor: Actor, today: date | None = None) -> None:
    """Generate the contract and deposit invoice PDFs, ready to check and send."""
    if Pipeline(e.pipeline_status) != Pipeline.QUOTE_ACCEPTED or b.status != BookingStatus.PENDING:
        raise DocumentError("wrong_stage", "Contracts are prepared after the quote is accepted.")
    today = today or utcnow().date()
    for c in db.scalars(
        select(Contract).where(
            Contract.booking_id == b.id, Contract.status == ContractStatus.PREPARED
        )
    ):
        c.status = ContractStatus.VOID
    old_inv = _active_deposit(db, b)
    if old_inv is not None:
        if old_inv.status != InvoiceStatus.PREPARED:
            raise DocumentError("invoice_issued", "The deposit invoice has already been sent.")
        old_inv.status = InvoiceStatus.VOID

    ctx = _context(db, b, e)
    terms = settings.get(db, "contract_terms")
    terms_html = terms["planner" if e.type == "planner" else "bride"]
    version = (
        db.scalar(select(func.max(Contract.version)).where(Contract.booking_id == b.id)) or 0
    ) + 1
    due = today + timedelta(days=int(settings.get(db, "deposit_due_days") or 7))
    surname = e.client_name.split()[-1] if e.client_name else "client"

    contract_pdf = pdf.html_to_pdf(
        pdf.render_html(
            "contract.html",
            ctx | {"version": version, "terms_html": terms_html, "deposit_due": long_date(due)},
        )
    )
    cdoc = storage.store(
        db,
        kind="contract",
        filename=f"Jstyle contract - {surname} - v{version}.pdf",
        data=contract_pdf,
        content_type="application/pdf",
        enquiry_id=e.id,
    )
    contract = Contract(
        booking_id=b.id,
        enquiry_id=e.id,
        version=version,
        status=ContractStatus.PREPARED,
        terms_html=terms_html,
        document_id=cdoc.id,
    )
    db.add(contract)

    number = next_invoice_number(db, today.year)
    invoice_pdf = pdf.html_to_pdf(
        pdf.render_html(
            "invoice.html",
            ctx
            | {
                "number": number,
                "issued": long_date(today),
                "due": long_date(due),
                "heading": "Deposit",
                "lines": [
                    {
                        "description": f"Deposit to reserve {long_date(e.wedding_date)}",
                        "amount": money(b.deposit_cents),
                    }
                ],
                "amount": money(b.deposit_cents),
            },
        )
    )
    idoc = storage.store(
        db,
        kind="invoice",
        filename=f"Jstyle invoice {number}.pdf",
        data=invoice_pdf,
        content_type="application/pdf",
        enquiry_id=e.id,
    )
    db.add(
        Invoice(
            number=number,
            booking_id=b.id,
            enquiry_id=e.id,
            kind=InvoiceKind.DEPOSIT,
            amount_cents=b.deposit_cents,
            due_on=due,
            status=InvoiceStatus.PREPARED,
            document_id=idoc.id,
        )
    )
    db.flush()
    write_audit(
        db,
        actor,
        "contract.prepare",
        entity_type="booking",
        entity_id=b.id,
        after={"contract_version": version, "invoice": number},
    )


def send(db: Session, b: Booking, e: Enquiry, actor: Actor) -> uuid.UUID:
    c = _active_contract(db, b)
    inv = _active_deposit(db, b)
    if c is None or inv is None or c.status != ContractStatus.PREPARED:
        raise DocumentError("not_prepared", "Prepare the contract and invoice first.")
    if inv.status != InvoiceStatus.PREPARED:
        raise DocumentError("invoice_issued", "The deposit invoice has already been sent.")
    c.status = ContractStatus.SENDING
    event_id = outbox.enqueue(
        db,
        "booking.send_contract",
        f"send_contract:{c.id}",
        {"contract_id": str(c.id), "invoice_id": str(inv.id), "enquiry_id": str(e.id)},
        aggregate_type="booking",
        aggregate_id=b.id,
    )
    assert event_id is not None
    write_audit(
        db,
        actor,
        "contract.send",
        entity_type="booking",
        entity_id=b.id,
        after={"contract_version": c.version, "invoice": inv.number},
    )
    return event_id


def on_sent(db: Session, c: Contract, inv: Invoice, actor: Actor) -> None:
    """Called by the worker after the email with both PDFs went out."""
    now = utcnow()
    c.status = ContractStatus.SENT
    c.sent_at = now
    inv.status = InvoiceStatus.ISSUED
    inv.issued_at = now
    e = db.get(Enquiry, c.enquiry_id)
    assert e is not None
    if Pipeline(e.pipeline_status) == Pipeline.QUOTE_ACCEPTED:
        transition(db, e, Pipeline.CONTRACT_DEPOSIT_PENDING, actor)


def on_send_failed(db: Session, c: Contract) -> None:
    if c.status == ContractStatus.SENDING:
        c.status = ContractStatus.PREPARED


def mark_signed(
    db: Session,
    c: Contract,
    actor: Actor,
    *,
    signed_on: date,
    method: str,
    note: str | None,
    evidence: tuple[str, str, bytes] | None,
) -> None:
    if c.status not in (ContractStatus.SENT, ContractStatus.PREPARED):
        raise DocumentError("wrong_status", f"A {c.status} contract can't be marked as signed.")
    if method not in SIGNED_METHODS:
        raise DocumentError("bad_method", "Choose how the contract was signed.")
    if signed_on > utcnow().date() + timedelta(days=1):
        raise DocumentError("future_date", "The signed date can't be in the future.")
    if evidence is not None:
        filename, content_type, data = evidence
        doc = storage.store(
            db,
            kind="signed_contract",
            filename=filename[:200] or "signed-contract",
            data=data,
            content_type=content_type,
            enquiry_id=c.enquiry_id,
        )
        c.signed_evidence_id = doc.id
    c.status = ContractStatus.SIGNED
    c.signed_on = signed_on
    c.signed_method = method
    c.signed_note = note
    c.marked_signed_at = utcnow()
    b = db.get(Booking, c.booking_id)
    e = db.get(Enquiry, c.enquiry_id)
    assert b is not None and e is not None
    b.contract_signed_at = c.marked_signed_at
    write_audit(
        db,
        actor,
        "contract.mark_signed",
        entity_type="contract",
        entity_id=c.id,
        after={
            "signed_on": signed_on.isoformat(),
            "method": method,
            "evidence": str(c.signed_evidence_id) if c.signed_evidence_id else None,
        },
    )
    bookings.try_book(db, b, e, actor)


def contract_dict(db: Session, c: Contract) -> dict[str, Any]:
    e = db.get(Enquiry, c.enquiry_id)
    return {
        "id": c.id,
        "booking_id": c.booking_id,
        "enquiry_id": c.enquiry_id,
        "client_name": e.client_name if e else None,
        "wedding_date": e.wedding_date if e else None,
        "version": c.version,
        "status": c.status,
        "document_id": c.document_id,
        "sent_at": c.sent_at,
        "signed_on": c.signed_on,
        "signed_method": c.signed_method,
        "signed_note": c.signed_note,
        "signed_evidence_id": c.signed_evidence_id,
        "created_at": c.created_at,
    }


def invoice_dict(db: Session, inv: Invoice) -> dict[str, Any]:
    e = db.get(Enquiry, inv.enquiry_id)
    return {
        "id": inv.id,
        "number": inv.number,
        "booking_id": inv.booking_id,
        "enquiry_id": inv.enquiry_id,
        "client_name": e.client_name if e else None,
        "kind": inv.kind,
        "amount_cents": inv.amount_cents,
        "due_on": inv.due_on,
        "status": inv.status,
        "document_id": inv.document_id,
        "issued_at": inv.issued_at,
        "created_at": inv.created_at,
    }


def document(db: Session, doc_id: uuid.UUID) -> Document | None:
    return db.get(Document, doc_id)
