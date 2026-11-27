from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.db import get_session
from app.modules.auth.deps import Account
from app.modules.email.models import EmailMessage, EmailThread
from app.modules.enquiries.models import Enquiry
from app.modules.inbox import service

router = APIRouter(tags=["inbox"])
DB = Annotated[Session, Depends(get_session)]
Cfg = Annotated[Settings, Depends(get_settings)]


def _thread(db: Session, thread_id: uuid.UUID) -> EmailThread:
    t = db.get(EmailThread, thread_id)
    if t is None:
        raise HTTPException(404, detail={"code": "not_found", "message": "Conversation not found."})
    return t


@router.get("/threads")
def list_threads(
    account: Account, db: DB, unread: bool = False, enquiry_id: uuid.UUID | None = None
) -> list[dict[str, Any]]:
    q = select(EmailThread).order_by(EmailThread.last_message_at.desc().nulls_last()).limit(200)
    if unread:
        q = q.where(EmailThread.unread.is_(True))
    if enquiry_id:
        q = q.where(EmailThread.enquiry_id == enquiry_id)
    return [service.thread_summary(db, t) for t in db.scalars(q)]


@router.get("/threads/unread-count")
def unread_count(account: Account, db: DB) -> dict[str, int]:
    n = len(db.scalars(select(EmailThread.id).where(EmailThread.unread.is_(True))).all())
    return {"unread": n}


@router.get("/threads/{thread_id}")
def get_thread(thread_id: uuid.UUID, account: Account, db: DB) -> dict[str, Any]:
    t = _thread(db, thread_id)
    msgs = db.scalars(
        select(EmailMessage).where(EmailMessage.thread_id == t.id).order_by(EmailMessage.sent_at)
    )
    return service.thread_summary(db, t) | {"messages": [service.message_dict(m) for m in msgs]}


@router.post("/threads/{thread_id}/read", status_code=204)
def mark_read(thread_id: uuid.UUID, account: Account, db: DB) -> None:
    _thread(db, thread_id).unread = False
    db.commit()


@router.post("/threads/{thread_id}/unread", status_code=204)
def mark_unread(thread_id: uuid.UUID, account: Account, db: DB) -> None:
    _thread(db, thread_id).unread = True
    db.commit()


class ReplyIn(BaseModel):
    body: str = Field(min_length=1, max_length=20000)


@router.post("/threads/{thread_id}/reply", status_code=202)
def reply(thread_id: uuid.UUID, body: ReplyIn, account: Account, db: DB) -> dict[str, Any]:
    t = _thread(db, thread_id)
    try:
        event_id = service.queue_reply(db, t, body.body, account.actor)
    except service.InboxError as exc:
        raise HTTPException(409, detail={"code": exc.code, "message": str(exc)}) from exc
    db.commit()
    return {"queued": True, "event_id": event_id}


class SimulateIn(BaseModel):
    body: str = Field(min_length=1, max_length=20000)


@router.post("/dev/enquiries/{enquiry_id}/simulate-reply", status_code=201)
def simulate_reply(
    enquiry_id: uuid.UUID, body: SimulateIn, account: Account, db: DB, settings: Cfg
) -> dict[str, Any]:
    """Local testing only: pretend the client replied to the latest email.

    Goes through the same matching code the Gmail sync uses.
    """
    if settings.env != "local":
        raise HTTPException(404)
    e = db.get(Enquiry, enquiry_id)
    if e is None:
        raise HTTPException(404, detail={"code": "not_found", "message": "Enquiry not found."})
    last = db.scalar(
        select(EmailMessage)
        .join(EmailThread, EmailThread.id == EmailMessage.thread_id)
        .where(EmailThread.enquiry_id == e.id, EmailMessage.direction == "outbound")
        .order_by(EmailMessage.sent_at.desc())
        .limit(1)
    )
    subject = f"Re: {last.subject}" if last else "Question about my wedding"
    result = service.ingest_inbound(
        db,
        service.InboundMail(
            rfc_message_id=f"<simulated-{uuid.uuid4()}@client.local>",
            from_addr=f"{e.client_name} <{e.email}>",
            to_addrs=[settings.allowed_email],
            subject=subject,
            body_text=body.body,
            in_reply_to=last.rfc_message_id if last else None,
            references=[last.rfc_message_id] if last else [],
        ),
    )
    db.commit()
    return {"status": result.status, "message_id": result.message_id}
