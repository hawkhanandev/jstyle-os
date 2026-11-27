from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.modules.auth.deps import Account
from app.modules.enquiries.models import Enquiry
from app.modules.quotes import service
from app.modules.quotes.models import Quote, QuoteStatus

router = APIRouter(tags=["quotes"])
DB = Annotated[Session, Depends(get_session)]


class CustomLineIn(BaseModel):
    description: str = Field(min_length=1, max_length=200)
    amount_cents: int = Field(ge=0)
    quantity: int = Field(default=1, ge=1, le=50)


class QuoteInputs(BaseModel):
    attendant_hair: int | None = Field(default=None, ge=0, le=50)
    attendant_makeup: int | None = Field(default=None, ge=0, le=50)
    trial: bool | None = None
    bridal_package: str | None = None
    travel_zone: str | None = None
    stylists_required: int | None = Field(default=None, ge=0, le=20)
    travel_fee_cents: int | None = Field(default=None, ge=0)
    custom_lines: list[CustomLineIn] | None = None
    note_to_client: str | None = Field(default=None, max_length=2000)


def _overrides(body: QuoteInputs) -> dict[str, Any]:
    return body.model_dump(exclude_unset=True)


def _fail(exc: service.QuoteError) -> HTTPException:
    status = 409 if exc.code != "region_unknown" else 422
    return HTTPException(
        status, detail={"code": exc.code, "message": str(exc), "details": exc.details}
    )


def _load(db: Session, quote_id: uuid.UUID) -> tuple[Quote, Enquiry]:
    q = db.get(Quote, quote_id)
    if q is None:
        raise HTTPException(404, detail={"code": "not_found", "message": "Quote not found."})
    e = db.get(Enquiry, q.enquiry_id)
    assert e is not None
    return q, e


@router.get("/enquiries/{enquiry_id}/quotes")
def list_quotes(enquiry_id: uuid.UUID, account: Account, db: DB) -> list[dict[str, Any]]:
    rows = db.scalars(
        select(Quote).where(Quote.enquiry_id == enquiry_id).order_by(Quote.version.desc())
    )
    return [service.to_dict(db, q) for q in rows]


@router.get("/quotes")
def approval_queue(
    account: Account, db: DB, status: QuoteStatus = QuoteStatus.AWAITING_APPROVAL
) -> list[dict[str, Any]]:
    rows = db.execute(
        select(Quote, Enquiry)
        .join(Enquiry, Enquiry.id == Quote.enquiry_id)
        .where(Quote.status == status)
        .order_by(Quote.submitted_at)
    ).all()
    return [
        service.to_dict(db, q)
        | {"client_name": e.client_name, "region": e.region, "wedding_date": e.wedding_date}
        for q, e in rows
    ]


@router.post("/enquiries/{enquiry_id}/quotes", status_code=201)
def create_quote(
    enquiry_id: uuid.UUID, body: QuoteInputs, account: Account, db: DB
) -> dict[str, Any]:
    e = db.get(Enquiry, enquiry_id)
    if e is None:
        raise HTTPException(404, detail={"code": "not_found", "message": "Enquiry not found."})
    try:
        q = service.create_draft(db, e, account.actor, _overrides(body))
    except service.QuoteError as exc:
        raise _fail(exc) from exc
    db.commit()
    return service.to_dict(db, q)


@router.get("/quotes/{quote_id}")
def get_quote(quote_id: uuid.UUID, account: Account, db: DB) -> dict[str, Any]:
    return service.to_dict(db, _load(db, quote_id)[0])


@router.patch("/quotes/{quote_id}")
def update_quote(
    quote_id: uuid.UUID, body: QuoteInputs, account: Account, db: DB
) -> dict[str, Any]:
    q, e = _load(db, quote_id)
    try:
        service.update_draft(db, q, e, account.actor, _overrides(body))
    except service.QuoteError as exc:
        raise _fail(exc) from exc
    db.commit()
    return service.to_dict(db, q)


@router.get("/quotes/{quote_id}/preview-email")
def preview_email(quote_id: uuid.UUID, account: Account, db: DB) -> dict[str, str]:
    q, e = _load(db, quote_id)
    if q.email_body_html:  # frozen at approval: show exactly what was sent
        return {"subject": q.email_subject or "", "html": q.email_body_html, "frozen": "true"}
    r = service.render_email(db, q, e)
    return {"subject": r.subject, "html": r.html, "frozen": "false"}


class SubmitIn(BaseModel):
    acknowledged_flags: list[str] = []


class NoteIn(BaseModel):
    note: str | None = Field(default=None, max_length=2000)


def _act(db: Session, quote_id: uuid.UUID, fn: Any, *args: Any) -> dict[str, Any]:
    q, e = _load(db, quote_id)
    try:
        fn(db, q, e, *args)
    except service.QuoteError as exc:
        raise _fail(exc) from exc
    db.commit()
    return service.to_dict(db, q)


@router.post("/quotes/{quote_id}/submit")
def submit(quote_id: uuid.UUID, body: SubmitIn, account: Account, db: DB) -> dict[str, Any]:
    return _act(db, quote_id, service.submit, account.actor, body.acknowledged_flags)


@router.post("/quotes/{quote_id}/approve")
def approve(quote_id: uuid.UUID, account: Account, db: DB) -> dict[str, Any]:
    return _act(db, quote_id, service.approve, account.actor)


@router.post("/quotes/{quote_id}/reject")
def reject(quote_id: uuid.UUID, body: NoteIn, account: Account, db: DB) -> dict[str, Any]:
    return _act(db, quote_id, service.reject, account.actor, body.note)


@router.post("/quotes/{quote_id}/withdraw")
def withdraw(quote_id: uuid.UUID, body: NoteIn, account: Account, db: DB) -> dict[str, Any]:
    return _act(db, quote_id, service.withdraw, account.actor, body.note)


@router.post("/quotes/{quote_id}/reprice")
def reprice(quote_id: uuid.UUID, account: Account, db: DB) -> dict[str, Any]:
    return _act(db, quote_id, service.reprice_on_active_card, account.actor)


@router.post("/quotes/{quote_id}/retry-send")
def retry_send(quote_id: uuid.UUID, account: Account, db: DB) -> dict[str, Any]:
    return _act(db, quote_id, service.retry_send, account.actor)
