"""Turns an `email.send` outbox event into a sent, stored email."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.db import utcnow
from app.modules.email import templates
from app.modules.email.mailer import Attachment, Mailer, OutgoingMail
from app.modules.email.models import EmailMessage, EmailThread
from app.modules.enquiries.models import CLOSED, Enquiry, Pipeline
from app.modules.platform import settings
from app.modules.platform.models import OutboxEvent
from app.modules.platform.outbox import PermanentError

REGION_NAMES = {"HI": "Hawaii", "OR": "Oregon"}


class Skip(Exception):
    """The email no longer applies (e.g. enquiry closed). Event is marked done, not sent."""


def message_id_for(event_id: uuid.UUID) -> str:
    return f"<outbox-{event_id}@jstyle-os>"


def _setting(db: Session, key: str) -> Any:
    return settings.get(db, key) or {}


def long_date(d: date | None) -> str:
    return f"{d:%A, %B} {d.day}, {d.year}" if d else ""


def base_context(db: Session, enquiry: Enquiry) -> dict[str, Any]:
    business = _setting(db, "business") or {}
    pay = _setting(db, "payment_instructions") or {}
    first = enquiry.client_name.split()[0] if enquiry.client_name else ""
    return {
        "client_first_name": first,
        "client_name": enquiry.client_name,
        "wedding_date": long_date(enquiry.wedding_date),
        "venue": enquiry.venue_name or "",
        "region_name": REGION_NAMES.get(enquiry.region or "", ""),
        "business_name": business.get("name", "Jstyle"),
        "business_email": business.get("email", ""),
        "business_phone": business.get("phone", ""),
        "venmo": pay.get("venmo", ""),
        "zelle": pay.get("zelle", ""),
    }


def from_address(db: Session, settings: Settings) -> str:
    business = _setting(db, "business") or {}
    name = business.get("name", "Jstyle")
    return f"{name} <{settings.allowed_email or 'owner@jstyle.local'}>"


def deliver(db: Session, event: OutboxEvent, mailer: Mailer, settings: Settings) -> EmailMessage:
    payload = event.payload
    rfc_id = message_id_for(event.id)
    existing = db.scalar(select(EmailMessage).where(EmailMessage.rfc_message_id == rfc_id))
    if existing is not None:
        return existing  # already sent on an earlier attempt

    enquiry = db.get(Enquiry, uuid.UUID(payload["enquiry_id"]))
    if enquiry is None:
        raise PermanentError("enquiry not found")
    key = payload["template"]
    if Pipeline(enquiry.pipeline_status) == Pipeline.CANCELLED:
        raise Skip("wedding cancelled")
    if key == "enquiry_ack":
        if Pipeline(enquiry.pipeline_status) in CLOSED:
            raise Skip("enquiry closed before the acknowledgement was sent")
        if enquiry.type == "planner":
            key = "planner_ack"

    context = base_context(db, enquiry) | payload.get("context", {})
    rendered = templates.render(db, key, context)
    return send_rendered(
        db,
        event,
        mailer,
        settings,
        enquiry,
        subject=rendered.subject,
        html=rendered.html,
        text=rendered.text,
        template_key=key,
    )


def send_rendered(
    db: Session,
    event: OutboxEvent,
    mailer: Mailer,
    settings: Settings,
    enquiry: Enquiry,
    *,
    subject: str,
    html: str,
    text: str,
    template_key: str | None,
    thread_id: uuid.UUID | None = None,
    attachments: list[Attachment] | None = None,
) -> EmailMessage:
    """Send exact, already-rendered content in the enquiry's thread and store it.

    Without `thread_id` the enquiry's most recent conversation is continued.
    """
    rfc_id = message_id_for(event.id)
    existing = db.scalar(select(EmailMessage).where(EmailMessage.rfc_message_id == rfc_id))
    if existing is not None:
        return existing
    thread = (
        db.get(EmailThread, thread_id)
        if thread_id
        else db.scalar(
            select(EmailThread)
            .where(EmailThread.enquiry_id == enquiry.id)
            .order_by(EmailThread.last_message_at.desc().nulls_last())
            .limit(1)
        )
    )
    previous = (
        db.scalars(
            select(EmailMessage.rfc_message_id)
            .where(EmailMessage.thread_id == thread.id)
            .order_by(EmailMessage.sent_at)
        ).all()
        if thread
        else []
    )
    mail = OutgoingMail(
        from_addr=from_address(db, settings),
        to=[enquiry.email],
        subject=subject,
        html=html,
        text=text,
        message_id=rfc_id,
        in_reply_to=previous[-1] if previous else None,
        references=list(previous[-10:]),
        provider_thread_id=thread.provider_thread_id if thread else None,
        attachments=attachments or [],
    )
    result = mailer.send(mail)

    now = utcnow()
    if thread is None:
        thread = EmailThread(
            enquiry_id=enquiry.id, subject=subject, provider_thread_id=result.provider_thread_id
        )
        db.add(thread)
        db.flush()
    elif thread.provider_thread_id is None and result.provider_thread_id:
        thread.provider_thread_id = result.provider_thread_id
    thread.last_message_at = now
    msg = EmailMessage(
        thread_id=thread.id,
        provider_message_id=result.provider_message_id,
        rfc_message_id=rfc_id,
        direction="outbound",
        from_addr=mail.from_addr,
        to_addrs=mail.to,
        subject=subject,
        body_html=html,
        body_text=text,
        sent_at=now,
        template_key=template_key,
        outbox_event_id=event.id,
    )
    db.add(msg)
    db.flush()
    return msg
