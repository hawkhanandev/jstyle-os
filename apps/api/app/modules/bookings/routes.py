from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.db import get_session, utcnow
from app.modules.auth.deps import Account
from app.modules.bookings import cancel, service
from app.modules.enquiries.models import Enquiry
from app.modules.quotes.models import Quote
from app.modules.scheduling import service as scheduling
from app.modules.scheduling.models import ScheduledEmail

router = APIRouter(tags=["bookings"])
DB = Annotated[Session, Depends(get_session)]


def _enquiry(db: Session, enquiry_id: uuid.UUID) -> Enquiry:
    e = db.get(Enquiry, enquiry_id)
    if e is None:
        raise HTTPException(404, detail={"code": "not_found", "message": "Enquiry not found."})
    return e


@router.get("/enquiries/{enquiry_id}/booking")
def get_booking(enquiry_id: uuid.UUID, account: Account, db: DB) -> dict[str, Any] | None:
    e = _enquiry(db, enquiry_id)
    b = service.for_enquiry(db, e.id)
    return service.to_dict(db, b, e) if b else None


@router.post("/quotes/{quote_id}/accept")
def accept(quote_id: uuid.UUID, account: Account, db: DB) -> dict[str, Any]:
    """Staff record an acceptance that came by phone, text or in person."""
    q = db.get(Quote, quote_id)
    if q is None:
        raise HTTPException(404, detail={"code": "not_found", "message": "Quote not found."})
    e = _enquiry(db, q.enquiry_id)
    try:
        b = service.accept_quote(db, q, e, account.actor, via="staff")
    except service.BookingError as exc:
        db.rollback()
        raise HTTPException(409, detail={"code": exc.code, "message": str(exc)}) from exc
    db.commit()
    return service.to_dict(db, b, e)


class StylistsIn(BaseModel):
    stylists_required: int = Field(ge=1, le=20)


@router.patch("/enquiries/{enquiry_id}/booking")
def update_booking(
    enquiry_id: uuid.UUID, body: StylistsIn, account: Account, db: DB
) -> dict[str, Any]:
    e = _enquiry(db, enquiry_id)
    b = service.for_enquiry(db, e.id)
    if b is None:
        raise HTTPException(404, detail={"code": "not_found", "message": "No booking yet."})
    service.set_stylists(db, b, e, body.stylists_required, account.actor)
    db.commit()
    return service.to_dict(db, b, e)


class CancelIn(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)


@router.post("/enquiries/{enquiry_id}/cancel-wedding")
def cancel_wedding(
    enquiry_id: uuid.UUID, body: CancelIn, account: Account, db: DB
) -> dict[str, int]:
    e = _enquiry(db, enquiry_id)
    try:
        result = cancel.cancel_wedding(db, e, body.reason, account.actor)
    except cancel.CancelError as exc:
        db.rollback()
        raise HTTPException(409, detail={"code": exc.code, "message": str(exc)}) from exc
    db.commit()
    return result


@router.get("/enquiries/{enquiry_id}/scheduled-emails")
def scheduled_emails(enquiry_id: uuid.UUID, account: Account, db: DB) -> list[dict[str, Any]]:
    rows = db.scalars(
        select(ScheduledEmail)
        .where(ScheduledEmail.enquiry_id == enquiry_id)
        .order_by(ScheduledEmail.send_at.desc())
    )
    return [scheduling.to_dict(s) for s in rows]


@router.post("/dev/scheduled-emails/{sid}/send-now")
def send_now(
    sid: uuid.UUID, account: Account, db: DB, settings: Annotated[Settings, Depends(get_settings)]
) -> dict[str, Any]:
    """Local testing only: make a scheduled email due now (the worker picks it up)."""
    if settings.env != "local":
        raise HTTPException(404)
    s = db.get(ScheduledEmail, sid)
    if s is None or s.status != "scheduled":
        raise HTTPException(404, detail={"code": "not_found", "message": "Nothing scheduled."})
    s.send_at = utcnow()
    db.commit()
    return scheduling.to_dict(s)
