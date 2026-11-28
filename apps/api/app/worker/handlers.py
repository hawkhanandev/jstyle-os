from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.db import utcnow
from app.modules.bookings import service as bookings
from app.modules.documents import service as documents
from app.modules.documents import storage
from app.modules.documents.models import Contract, ContractStatus, Document, Invoice
from app.modules.email import templates
from app.modules.email.mailer import Attachment, Mailer
from app.modules.email.send import Skip, base_context, deliver, long_date, send_rendered
from app.modules.enquiries.models import Enquiry
from app.modules.operations import service as operations
from app.modules.platform import settings
from app.modules.platform.audit import SYSTEM
from app.modules.platform.models import OutboxEvent
from app.modules.platform.outbox import PermanentError
from app.modules.quotes import service as quotes
from app.modules.quotes.models import Quote, QuoteStatus
from app.modules.quotes.service import money


@dataclass
class Deps:
    settings: Settings
    mailer: Mailer


Handler = Callable[[Session, OutboxEvent, Deps], None]


def email_send(db: Session, event: OutboxEvent, deps: Deps) -> None:
    deliver(db, event, deps.mailer, deps.settings)


def email_reply(db: Session, event: OutboxEvent, deps: Deps) -> None:
    """A reply Jessica typed in the Inbox. Sent as written, in the same conversation."""
    p = event.payload
    e = db.get(Enquiry, uuid.UUID(p["enquiry_id"]))
    if e is None:
        raise PermanentError("enquiry not found")
    send_rendered(
        db,
        event,
        deps.mailer,
        deps.settings,
        e,
        subject=p["subject"],
        html=p["html"],
        text=p["text"],
        template_key=None,
        thread_id=uuid.UUID(p["thread_id"]),
    )


def quote_send(db: Session, event: OutboxEvent, deps: Deps) -> None:
    q = db.get(Quote, uuid.UUID(event.payload["quote_id"]), with_for_update=True)
    if q is None:
        raise PermanentError("quote not found")
    if q.status == QuoteStatus.SENT:
        return
    if q.status != QuoteStatus.SENDING or q.outbox_event_id != event.id:
        raise Skip(f"quote is {q.status}, not waiting to send")
    e = db.get(Enquiry, q.enquiry_id)
    assert e is not None and q.email_subject and q.email_body_html
    msg = send_rendered(
        db,
        event,
        deps.mailer,
        deps.settings,
        e,
        subject=q.email_subject,
        html=q.email_body_html,
        text=q.email_body_text or "",
        template_key="quote_revision" if q.supersedes_quote_id else "quote",
    )
    quotes.mark_sent(db, q, msg.id, SYSTEM)


def booking_send_contract(db: Session, event: OutboxEvent, deps: Deps) -> None:
    """One email with the contract and the deposit invoice attached."""
    c = db.get(Contract, uuid.UUID(event.payload["contract_id"]), with_for_update=True)
    inv = db.get(Invoice, uuid.UUID(event.payload["invoice_id"]))
    if c is None or inv is None:
        raise PermanentError("contract or invoice not found")
    if c.status == ContractStatus.SENT:
        return
    if c.status != ContractStatus.SENDING:
        raise Skip(f"contract is {c.status}, not waiting to send")
    e = db.get(Enquiry, c.enquiry_id)
    assert e is not None
    files = []
    for doc_id in (c.document_id, inv.document_id):
        doc = db.get(Document, doc_id)
        assert doc is not None
        files.append(Attachment(doc.filename, doc.content_type, storage.read(doc)))
    context = base_context(db, e) | {
        "deposit": money(inv.amount_cents),
        "deposit_due": long_date(inv.due_on),
        "invoice_number": inv.number,
    }
    rendered = templates.render(db, "contract_invoice", context)
    send_rendered(
        db,
        event,
        deps.mailer,
        deps.settings,
        e,
        subject=rendered.subject,
        html=rendered.html,
        text=rendered.text,
        template_key="contract_invoice",
        attachments=files,
    )
    documents.on_sent(db, c, inv, SYSTEM)


def booking_document_email(db: Session, event: OutboxEvent, deps: Deps) -> None:
    """Preparation guide, balance invoice or final timeline: a PDF made now and attached."""
    p = event.payload
    e = db.get(Enquiry, uuid.UUID(p["enquiry_id"]))
    if e is None:
        raise PermanentError("enquiry not found")
    b = bookings.for_enquiry(db, e.id)
    if b is None:
        raise Skip("no booking")
    surname = e.client_name.split()[-1] if e.client_name else "client"
    plan = operations.plan_for(db, b)
    context = base_context(db, e)
    doc_kind = p.get("doc")
    if doc_kind == "prep_guide":
        doc = documents.booking_pdf(
            db,
            b,
            e,
            "prep_guide.html",
            "prep_guide",
            f"Jstyle preparation guide - {surname}.pdf",
            {
                "getting_ready": plan.getting_ready_address,
                "guide_html": settings.get(db, "prep_guide_html"),
            },
        )
    elif doc_kind == "balance_invoice":
        owed = operations.outstanding(db, b)
        if owed == 0:
            raise Skip("balance already paid")
        inv = documents.issue_balance_invoice(db, b, e, owed, utcnow().date())
        doc = db.get(Document, inv.document_id)  # type: ignore[assignment]
        context |= {"balance": money(owed), "invoice_number": inv.number}
    elif doc_kind == "final_timeline":
        if operations.final_timeline_blockers(db, b):
            raise Skip("final timeline blocked")
        doc = documents.booking_pdf(
            db,
            b,
            e,
            "timeline.html",
            "final_timeline",
            f"Jstyle final timeline - {surname}.pdf",
            {
                "getting_ready": plan.getting_ready_address,
                "timeline": plan.timeline,
                "notes": plan.notes,
            },
        )
        plan.final_timeline_sent_at = utcnow()
    else:
        raise PermanentError(f"unknown document {doc_kind}")
    assert doc is not None
    rendered = templates.render(db, p["template"], context)
    send_rendered(
        db,
        event,
        deps.mailer,
        deps.settings,
        e,
        subject=rendered.subject,
        html=rendered.html,
        text=rendered.text,
        template_key=p["template"],
        attachments=[Attachment(doc.filename, doc.content_type, storage.read(doc))],
    )


def booking_send_contract_failed(db: Session, event: OutboxEvent) -> None:
    c = db.get(Contract, uuid.UUID(event.payload["contract_id"]))
    if c is not None:
        documents.on_send_failed(db, c)


def quote_send_failed(db: Session, event: OutboxEvent) -> None:
    q = db.get(Quote, uuid.UUID(event.payload["quote_id"]))
    if q is not None and q.status == QuoteStatus.SENDING:
        quotes.mark_send_failed(db, q, event.last_error or "send failed")


HANDLERS: dict[str, Handler] = {
    "email.send": email_send,
    "email.reply": email_reply,
    "quote.send": quote_send,
    "booking.send_contract": booking_send_contract,
    "booking.document_email": booking_document_email,
}

# Called when an event ends in failed or dead, so the business record shows the failure.
ON_GIVE_UP: dict[str, Callable[[Session, OutboxEvent], None]] = {
    "quote.send": quote_send_failed,
    "booking.send_contract": booking_send_contract_failed,
}
