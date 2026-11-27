"""Client conversations: inbound matching, staff replies, read state.

`ingest_inbound` is what the Gmail sync calls for every new message. It only ever
attaches mail to an existing enquiry; unrelated mail is ignored and never creates one.
"""

from __future__ import annotations

import html
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from email.utils import parseaddr
from typing import Any

import nh3
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import utcnow
from app.modules.email.models import EmailMessage, EmailThread
from app.modules.enquiries.models import CLOSED, Enquiry, Pipeline
from app.modules.platform import outbox
from app.modules.platform.audit import Actor, write_audit
from app.modules.platform.models import OutboxEvent, OutboxStatus


class InboxError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class InboundMail:
    rfc_message_id: str
    from_addr: str
    to_addrs: list[str]
    subject: str
    body_text: str
    body_html: str | None = None
    in_reply_to: str | None = None
    references: list[str] = field(default_factory=list)
    sent_at: datetime | None = None
    provider_message_id: str | None = None
    provider_thread_id: str | None = None


@dataclass(frozen=True)
class IngestResult:
    status: str  # attached | duplicate | ignored
    message_id: uuid.UUID | None = None
    enquiry_id: uuid.UUID | None = None


def _thread_by_reference(db: Session, mail: InboundMail) -> EmailThread | None:
    if mail.provider_thread_id:
        t = db.scalar(
            select(EmailThread).where(EmailThread.provider_thread_id == mail.provider_thread_id)
        )
        if t:
            return t
    refs = [r for r in [mail.in_reply_to, *reversed(mail.references)] if r]
    if not refs:
        return None
    thread_id = db.scalar(
        select(EmailMessage.thread_id).where(EmailMessage.rfc_message_id.in_(refs)).limit(1)
    )
    return db.get(EmailThread, thread_id) if thread_id else None


def _enquiry_by_sender(db: Session, sender: str) -> Enquiry | None:
    """Most recent open enquiry from this address. Closed ones only if nothing is open."""
    rows = db.scalars(
        select(Enquiry)
        .where(func.lower(Enquiry.email) == sender.lower())
        .order_by(Enquiry.created_at.desc())
    ).all()
    for e in rows:
        if Pipeline(e.pipeline_status) not in CLOSED:
            return e
    return rows[0] if rows else None


def ingest_inbound(db: Session, mail: InboundMail) -> IngestResult:
    existing = db.scalar(
        select(EmailMessage).where(EmailMessage.rfc_message_id == mail.rfc_message_id)
    )
    if existing is not None:
        return IngestResult("duplicate", existing.id)

    sender = parseaddr(mail.from_addr)[1] or mail.from_addr
    thread = _thread_by_reference(db, mail)
    enquiry = db.get(Enquiry, thread.enquiry_id) if thread and thread.enquiry_id else None
    if thread is None:
        enquiry = _enquiry_by_sender(db, sender)
        if enquiry is None:
            return IngestResult("ignored")
        thread = EmailThread(
            enquiry_id=enquiry.id,
            subject=mail.subject[:300],
            provider_thread_id=mail.provider_thread_id,
        )
        db.add(thread)
        db.flush()

    when = mail.sent_at or utcnow()
    msg = EmailMessage(
        thread_id=thread.id,
        provider_message_id=mail.provider_message_id,
        rfc_message_id=mail.rfc_message_id,
        direction="inbound",
        from_addr=mail.from_addr[:320],
        to_addrs=mail.to_addrs,
        subject=mail.subject[:300],
        body_html=nh3.clean(mail.body_html) if mail.body_html else None,
        body_text=mail.body_text,
        sent_at=when,
    )
    db.add(msg)
    thread.unread = True
    if thread.last_message_at is None or when > thread.last_message_at:
        thread.last_message_at = when
    db.flush()
    return IngestResult("attached", msg.id, enquiry.id if enquiry else None)


def text_to_html(text: str) -> str:
    paragraphs = [p for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]
    return "".join(f"<p>{html.escape(p).replace(chr(10), '<br>')}</p>" for p in paragraphs)


def queue_reply(db: Session, thread: EmailThread, body: str, actor: Actor) -> uuid.UUID:
    if not body.strip():
        raise InboxError("empty", "Write a reply first.")
    if thread.enquiry_id is None:
        raise InboxError("no_enquiry", "This conversation isn't linked to an enquiry.")
    subject = (
        thread.subject if thread.subject.lower().startswith("re:") else f"Re: {thread.subject}"
    )
    key = f"reply:{thread.id}:{uuid.uuid4()}"
    event_id = outbox.enqueue(
        db,
        "email.reply",
        key,
        {
            "enquiry_id": str(thread.enquiry_id),
            "thread_id": str(thread.id),
            "subject": subject,
            "text": body.strip(),
            "html": text_to_html(body),
        },
        aggregate_type="email_thread",
        aggregate_id=thread.id,
    )
    assert event_id is not None
    thread.unread = False
    write_audit(
        db,
        actor,
        "email.reply_queued",
        entity_type="email_thread",
        entity_id=thread.id,
        after={"subject": subject, "chars": len(body)},
    )
    return event_id


def snippet(msg: EmailMessage | None, length: int = 140) -> str:
    if msg is None:
        return ""
    text = msg.body_text or re.sub(r"<[^>]+>", " ", msg.body_html or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:length]


def thread_summary(db: Session, t: EmailThread) -> dict[str, Any]:
    last = db.scalar(
        select(EmailMessage)
        .where(EmailMessage.thread_id == t.id)
        .order_by(EmailMessage.sent_at.desc())
        .limit(1)
    )
    e = db.get(Enquiry, t.enquiry_id) if t.enquiry_id else None
    pending = db.scalar(
        select(func.count())
        .select_from(OutboxEvent)
        .where(
            OutboxEvent.aggregate_id == t.id,
            OutboxEvent.kind == "email.reply",
            OutboxEvent.status.in_([OutboxStatus.PENDING, OutboxStatus.IN_PROGRESS]),
        )
    )
    return {
        "id": t.id,
        "subject": t.subject,
        "unread": t.unread,
        "last_message_at": t.last_message_at,
        "last_direction": last.direction if last else None,
        "snippet": snippet(last),
        "enquiry_id": t.enquiry_id,
        "client_name": e.client_name if e else None,
        "client_email": e.email if e else None,
        "pipeline_status": e.pipeline_status if e else None,
        "replies_sending": pending or 0,
    }


def message_dict(m: EmailMessage) -> dict[str, Any]:
    return {
        "id": m.id,
        "direction": m.direction,
        "from_addr": m.from_addr,
        "to_addrs": m.to_addrs,
        "subject": m.subject,
        "body_html": m.body_html,
        "body_text": m.body_text,
        "sent_at": m.sent_at,
        "template_key": m.template_key,
    }
