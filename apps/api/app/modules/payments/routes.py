from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.modules.auth.deps import Account
from app.modules.bookings import service as bookings
from app.modules.enquiries.models import Enquiry
from app.modules.payments import service
from app.modules.payments.models import Payment, PaymentMethod, PaymentStatus

router = APIRouter(tags=["payments"])
DB = Annotated[Session, Depends(get_session)]


def _fail(exc: service.PaymentError) -> HTTPException:
    return HTTPException(409, detail={"code": exc.code, "message": str(exc)})


class PaymentIn(BaseModel):
    method: PaymentMethod
    amount_cents: int = Field(gt=0, le=10_000_000)
    received_on: date
    invoice_id: uuid.UUID | None = None
    reference: str | None = Field(default=None, max_length=200)
    note: str | None = Field(default=None, max_length=2000)
    verify: bool = False


class StatusIn(BaseModel):
    reason: str | None = Field(default=None, max_length=2000)


def _payments(db: Session, enquiry_id: uuid.UUID) -> dict[str, Any]:
    b = bookings.for_enquiry(db, enquiry_id)
    if b is None:
        raise HTTPException(404, detail={"code": "not_found", "message": "No booking yet."})
    rows = db.scalars(
        select(Payment)
        .where(Payment.booking_id == b.id)
        .order_by(Payment.received_on.desc(), Payment.created_at.desc())
    )
    return {
        "summary": service.summary(db, b),
        "payments": [service.to_dict(db, p) for p in rows],
    }


@router.get("/enquiries/{enquiry_id}/payments")
def list_for_enquiry(enquiry_id: uuid.UUID, account: Account, db: DB) -> dict[str, Any]:
    return _payments(db, enquiry_id)


@router.post("/enquiries/{enquiry_id}/payments", status_code=201)
def record(enquiry_id: uuid.UUID, body: PaymentIn, account: Account, db: DB) -> dict[str, Any]:
    e = db.get(Enquiry, enquiry_id)
    b = bookings.for_enquiry(db, enquiry_id) if e else None
    if e is None or b is None:
        raise HTTPException(404, detail={"code": "not_found", "message": "No booking yet."})
    try:
        service.record(db, b, e, account.actor, **body.model_dump())
    except service.PaymentError as exc:
        db.rollback()
        raise _fail(exc) from exc
    db.commit()
    return _payments(db, enquiry_id)


@router.get("/payments")
def list_all(account: Account, db: DB, status: PaymentStatus | None = None) -> list[dict[str, Any]]:
    q = select(Payment).order_by(Payment.created_at.desc()).limit(300)
    if status:
        q = q.where(Payment.status == status)
    return [service.to_dict(db, p) for p in db.scalars(q)]


def _set(
    db: Session, pid: uuid.UUID, target: PaymentStatus, account: Any, reason: str | None
) -> dict[str, Any]:
    p = db.get(Payment, pid)
    if p is None:
        raise HTTPException(404, detail={"code": "not_found", "message": "Payment not found."})
    try:
        service.set_status(db, p, target, account.actor, reason)
    except service.PaymentError as exc:
        db.rollback()
        raise _fail(exc) from exc
    db.commit()
    return service.to_dict(db, p)


@router.post("/payments/{pid}/verify")
def verify(pid: uuid.UUID, account: Account, db: DB) -> dict[str, Any]:
    return _set(db, pid, PaymentStatus.VERIFIED, account, None)


@router.post("/payments/{pid}/reject")
def reject(pid: uuid.UUID, body: StatusIn, account: Account, db: DB) -> dict[str, Any]:
    return _set(db, pid, PaymentStatus.REJECTED, account, body.reason)


@router.post("/payments/{pid}/void")
def void(pid: uuid.UUID, body: StatusIn, account: Account, db: DB) -> dict[str, Any]:
    return _set(db, pid, PaymentStatus.VOID, account, body.reason)


@router.post("/payments/{pid}/reopen")
def reopen(pid: uuid.UUID, account: Account, db: DB) -> dict[str, Any]:
    return _set(db, pid, PaymentStatus.RECORDED, account, None)
