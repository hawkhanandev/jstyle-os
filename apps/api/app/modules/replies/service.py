from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import utcnow
from app.modules.bookings import service as bookings
from app.modules.email.models import EmailMessage
from app.modules.enquiries.models import Enquiry, Pipeline
from app.modules.enquiries.pipeline import transition
from app.modules.platform.audit import Actor, write_audit
from app.modules.quotes import service as quotes
from app.modules.replies.classify import classify
from app.modules.replies.models import Intent, ReplySuggestion, SuggestionStatus

QUOTE_STAGES = {
    Pipeline.QUOTE_SENT,
    Pipeline.DISCUSSION_REVISION,
    Pipeline.QUOTE_DRAFT,
    Pipeline.AWAITING_APPROVAL,
}


class ReplyError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def on_inbound(db: Session, e: Enquiry, msg: EmailMessage) -> ReplySuggestion | None:
    # Replies are only read for intent while a quote is out with the client.
    if quotes.current_sent(db, e.id) is None:
        return None
    c = classify(msg.body_text or "")
    s = ReplySuggestion(
        enquiry_id=e.id,
        message_id=msg.id,
        intent=c.intent.value,
        confidence=c.confidence,
        matched=c.matched[:200] if c.matched else None,
        status=SuggestionStatus.PENDING,
    )
    db.add(s)
    db.flush()
    return s


def confirm(db: Session, s: ReplySuggestion, intent: Intent, actor: Actor) -> None:
    """Apply what the reply means. Staff may correct the suggested intent."""
    if s.status != SuggestionStatus.PENDING:
        raise ReplyError("resolved", "This reply has already been handled.")
    e = db.get(Enquiry, s.enquiry_id)
    assert e is not None
    status = Pipeline(e.pipeline_status)
    if intent == Intent.ACCEPT:
        q = quotes.current_sent(db, e.id)
        if q is None:
            raise ReplyError("no_quote", "There is no sent quote to accept.")
        try:
            bookings.accept_quote(db, q, e, actor, via="reply", message_id=s.message_id)
        except bookings.BookingError as exc:
            raise ReplyError(exc.code, str(exc)) from exc
    elif intent == Intent.CHANGE_REQUEST:
        if status == Pipeline.QUOTE_SENT:
            transition(
                db, e, Pipeline.DISCUSSION_REVISION, actor, reason="Client asked for changes"
            )
    elif intent == Intent.DECLINE and status in QUOTE_STAGES:
        open_q = quotes.open_quote(db, e.id)
        if open_q is not None:
            quotes.withdraw(db, open_q, e, actor, "Client declined")
        transition(db, e, Pipeline.LOST_DECLINED, actor, reason="Client declined by email")
    s.status = SuggestionStatus.CONFIRMED
    s.applied_intent = intent.value
    s.resolved_at = utcnow()
    write_audit(
        db,
        actor,
        "reply.confirm",
        entity_type="reply_suggestion",
        entity_id=s.id,
        after={"suggested": s.intent, "applied": intent.value},
    )


def dismiss(db: Session, s: ReplySuggestion, actor: Actor) -> None:
    if s.status != SuggestionStatus.PENDING:
        raise ReplyError("resolved", "This reply has already been handled.")
    s.status = SuggestionStatus.DISMISSED
    s.resolved_at = utcnow()
    write_audit(db, actor, "reply.dismiss", entity_type="reply_suggestion", entity_id=s.id)


def to_dict(db: Session, s: ReplySuggestion) -> dict[str, Any]:
    msg = db.get(EmailMessage, s.message_id)
    e = db.get(Enquiry, s.enquiry_id)
    return {
        "id": s.id,
        "enquiry_id": s.enquiry_id,
        "client_name": e.client_name if e else None,
        "pipeline_status": e.pipeline_status if e else None,
        "intent": s.intent,
        "confidence": s.confidence,
        "matched": s.matched,
        "status": s.status,
        "applied_intent": s.applied_intent,
        "created_at": s.created_at,
        "message": {
            "id": msg.id,
            "thread_id": msg.thread_id,
            "subject": msg.subject,
            "body_text": msg.body_text,
            "sent_at": msg.sent_at,
        }
        if msg
        else None,
    }


def pending(db: Session, enquiry_id: Any = None) -> list[ReplySuggestion]:
    q = select(ReplySuggestion).where(ReplySuggestion.status == SuggestionStatus.PENDING)
    if enquiry_id:
        q = q.where(ReplySuggestion.enquiry_id == enquiry_id)
    return list(db.scalars(q.order_by(ReplySuggestion.created_at)))
