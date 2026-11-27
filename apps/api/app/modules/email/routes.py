from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.modules.auth.deps import Account
from app.modules.email import templates
from app.modules.email.defaults import DEFAULT_TEMPLATES
from app.modules.email.models import EmailTemplate
from app.modules.email.send import base_context
from app.modules.enquiries.models import Enquiry
from app.modules.platform import outbox
from app.modules.platform.audit import write_audit
from app.modules.platform.models import OutboxEvent, OutboxStatus

router = APIRouter(tags=["email"])
DB = Annotated[Session, Depends(get_session)]

SAMPLE_QUOTE = {
    "lines": [
        {"description": "Bridal hair and makeup package", "quantity": 1, "amount": "$325"},
        {"description": "Attendant hair", "quantity": 2, "amount": "$240"},
        {"description": "Attendant makeup", "quantity": 2, "amount": "$260"},
        {"description": "Travel (per stylist)", "quantity": 1, "amount": "$75"},
    ],
    "total": "$900",
    "deposit": "$100",
    "balance": "$800",
}
SAMPLE_CONTEXT: dict[str, Any] = {
    "client_first_name": "Kailani",
    "client_name": "Kailani Akana",
    "wedding_date": "Saturday, June 12, 2027",
    "venue": "Kualoa Ranch",
    "region_name": "Hawaii",
    "business_name": "Jstyle Hair & Makeup",
    "business_email": "",
    "business_phone": "",
    "venmo": "@jstyle",
    "zelle": "pay@jstyle.example",
    "quote": SAMPLE_QUOTE,
    "deposit": "$100",
    "deposit_due": "June 1, 2026",
    "balance": "$800",
    "trial_date": "Friday, May 1, 2027",
    "trial_location": "the studio",
}


class TemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    key: str
    version: int
    name: str
    subject: str
    body: str
    is_active: bool
    created_at: datetime


@router.get("/templates")
def list_templates(account: Account, db: DB) -> list[TemplateOut]:
    rows = db.scalars(
        select(EmailTemplate).where(EmailTemplate.is_active).order_by(EmailTemplate.name)
    )
    return [TemplateOut.model_validate(r) for r in rows]


@router.get("/templates/{key}/versions")
def template_versions(key: str, account: Account, db: DB) -> list[TemplateOut]:
    rows = db.scalars(
        select(EmailTemplate).where(EmailTemplate.key == key).order_by(EmailTemplate.version.desc())
    )
    return [TemplateOut.model_validate(r) for r in rows]


class TemplateIn(BaseModel):
    subject: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1, max_length=50_000)


@router.post("/templates/{key}/versions", status_code=201)
def save_template(key: str, body: TemplateIn, account: Account, db: DB) -> TemplateOut:
    if key not in DEFAULT_TEMPLATES:
        raise HTTPException(404, detail={"code": "not_found", "message": "Unknown template."})
    try:
        row = templates.save_version(
            db, account.actor, key, DEFAULT_TEMPLATES[key][0], body.subject, body.body
        )
    except templates.TemplateInvalid as exc:
        raise HTTPException(422, detail={"code": "template_invalid", "message": str(exc)}) from exc
    db.commit()
    return TemplateOut.model_validate(row)


class PreviewIn(TemplateIn):
    enquiry_id: uuid.UUID | None = None


@router.post("/templates/preview")
def preview_template(body: PreviewIn, account: Account, db: DB) -> dict[str, str]:
    context = dict(SAMPLE_CONTEXT)
    if body.enquiry_id and (e := db.get(Enquiry, body.enquiry_id)):
        context |= base_context(db, e)
    try:
        subject, html = templates.render_strings(body.subject, body.body, context)
    except templates.TemplateInvalid as exc:
        raise HTTPException(422, detail={"code": "template_invalid", "message": str(exc)}) from exc
    return {"subject": subject, "html": html}


class OutboxOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: str
    status: str
    attempts: int
    last_error: str | None
    payload: dict[str, Any]
    next_attempt_at: datetime
    created_at: datetime


@router.get("/outbox")
def list_outbox(account: Account, db: DB, status: OutboxStatus | None = None) -> list[OutboxOut]:
    stmt = select(OutboxEvent).order_by(OutboxEvent.created_at.desc()).limit(200)
    if status:
        stmt = stmt.where(OutboxEvent.status == status)
    return [OutboxOut.model_validate(r) for r in db.scalars(stmt)]


def _event(db: Session, event_id: uuid.UUID) -> OutboxEvent:
    e = db.get(OutboxEvent, event_id)
    if e is None:
        raise HTTPException(404, detail={"code": "not_found", "message": "Event not found."})
    return e


@router.post("/outbox/{event_id}/retry")
def retry_event(event_id: uuid.UUID, account: Account, db: DB) -> OutboxOut:
    e = _event(db, event_id)
    if e.status not in (OutboxStatus.FAILED, OutboxStatus.DEAD, OutboxStatus.PAUSED):
        raise HTTPException(409, detail={"code": "not_retryable", "message": "Not failed."})
    outbox.retry(e)
    write_audit(db, account.actor, "outbox.retry", entity_type="outbox_event", entity_id=e.id)
    db.commit()
    return OutboxOut.model_validate(e)


@router.post("/outbox/{event_id}/cancel")
def cancel_event(event_id: uuid.UUID, account: Account, db: DB) -> OutboxOut:
    e = _event(db, event_id)
    if e.status in (OutboxStatus.DONE, OutboxStatus.IN_PROGRESS):
        raise HTTPException(
            409, detail={"code": "not_cancellable", "message": "Already running or done."}
        )
    e.status = OutboxStatus.DEAD
    e.last_error = "cancelled by staff"
    write_audit(db, account.actor, "outbox.cancel", entity_type="outbox_event", entity_id=e.id)
    db.commit()
    return OutboxOut.model_validate(e)
