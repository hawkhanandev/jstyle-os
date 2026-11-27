from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.modules.email.mailer import Mailer
from app.modules.email.send import Skip, deliver, send_rendered
from app.modules.enquiries.models import Enquiry
from app.modules.platform.audit import SYSTEM
from app.modules.platform.models import OutboxEvent
from app.modules.platform.outbox import PermanentError
from app.modules.quotes import service as quotes
from app.modules.quotes.models import Quote, QuoteStatus


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


def quote_send_failed(db: Session, event: OutboxEvent) -> None:
    q = db.get(Quote, uuid.UUID(event.payload["quote_id"]))
    if q is not None and q.status == QuoteStatus.SENDING:
        quotes.mark_send_failed(db, q, event.last_error or "send failed")


HANDLERS: dict[str, Handler] = {
    "email.send": email_send,
    "email.reply": email_reply,
    "quote.send": quote_send,
}

# Called when an event ends in failed or dead, so the business record shows the failure.
ON_GIVE_UP: dict[str, Callable[[Session, OutboxEvent], None]] = {
    "quote.send": quote_send_failed,
}
