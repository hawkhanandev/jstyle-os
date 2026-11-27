from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated, Any
from urllib.parse import quote as urlquote

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.modules.auth.deps import Account
from app.modules.bookings import service as bookings
from app.modules.bookings.models import Booking
from app.modules.documents import service, storage
from app.modules.documents.models import Contract, Document, Invoice
from app.modules.enquiries.models import Enquiry

router = APIRouter(tags=["documents"])
DB = Annotated[Session, Depends(get_session)]
MAX_UPLOAD = 15 * 1024 * 1024
EVIDENCE_TYPES = {"application/pdf", "image/jpeg", "image/png", "image/heic", "image/webp"}


def _fail(exc: service.DocumentError) -> HTTPException:
    return HTTPException(409, detail={"code": exc.code, "message": str(exc)})


def _booking(db: Session, enquiry_id: uuid.UUID) -> tuple[Booking, Enquiry]:
    e = db.get(Enquiry, enquiry_id)
    b = bookings.for_enquiry(db, enquiry_id) if e else None
    if e is None or b is None:
        raise HTTPException(404, detail={"code": "not_found", "message": "No booking yet."})
    return b, e


def _paperwork(db: Session, enquiry_id: uuid.UUID) -> dict[str, Any]:
    contracts = db.scalars(
        select(Contract).where(Contract.enquiry_id == enquiry_id).order_by(Contract.version.desc())
    )
    invoices = db.scalars(
        select(Invoice).where(Invoice.enquiry_id == enquiry_id).order_by(Invoice.created_at.desc())
    )
    return {
        "contracts": [service.contract_dict(db, c) for c in contracts],
        "invoices": [service.invoice_dict(db, i) for i in invoices],
    }


@router.get("/enquiries/{enquiry_id}/paperwork")
def paperwork(enquiry_id: uuid.UUID, account: Account, db: DB) -> dict[str, Any]:
    return _paperwork(db, enquiry_id)


@router.post("/enquiries/{enquiry_id}/contract/prepare")
def prepare(enquiry_id: uuid.UUID, account: Account, db: DB) -> dict[str, Any]:
    b, e = _booking(db, enquiry_id)
    try:
        service.prepare(db, b, e, account.actor)
    except service.DocumentError as exc:
        db.rollback()
        raise _fail(exc) from exc
    db.commit()
    return _paperwork(db, enquiry_id)


@router.post("/enquiries/{enquiry_id}/contract/send", status_code=202)
def send(enquiry_id: uuid.UUID, account: Account, db: DB) -> dict[str, Any]:
    b, e = _booking(db, enquiry_id)
    try:
        service.send(db, b, e, account.actor)
    except service.DocumentError as exc:
        db.rollback()
        raise _fail(exc) from exc
    db.commit()
    return _paperwork(db, enquiry_id)


@router.post("/contracts/{contract_id}/mark-signed")
async def mark_signed(
    contract_id: uuid.UUID,
    account: Account,
    db: DB,
    signed_on: Annotated[date, Form()],
    method: Annotated[str, Form()],
    note: Annotated[str | None, Form(max_length=2000)] = None,
    evidence: Annotated[UploadFile | None, File()] = None,
) -> dict[str, Any]:
    c = db.get(Contract, contract_id)
    if c is None:
        raise HTTPException(404, detail={"code": "not_found", "message": "Contract not found."})
    file: tuple[str, str, bytes] | None = None
    if evidence is not None and evidence.filename:
        data = await evidence.read(MAX_UPLOAD + 1)
        if len(data) > MAX_UPLOAD:
            raise HTTPException(413, detail={"code": "too_large", "message": "Max 15 MB."})
        ctype = evidence.content_type or ""
        if ctype not in EVIDENCE_TYPES:
            raise HTTPException(
                422, detail={"code": "bad_type", "message": "Upload a PDF or a photo."}
            )
        file = (evidence.filename, ctype, data)
    try:
        service.mark_signed(
            db, c, account.actor, signed_on=signed_on, method=method, note=note, evidence=file
        )
    except service.DocumentError as exc:
        db.rollback()
        raise _fail(exc) from exc
    db.commit()
    return service.contract_dict(db, c)


@router.get("/contracts")
def list_contracts(account: Account, db: DB, status: str | None = None) -> list[dict[str, Any]]:
    q = select(Contract).order_by(Contract.created_at.desc()).limit(300)
    if status:
        q = q.where(Contract.status == status)
    return [service.contract_dict(db, c) for c in db.scalars(q)]


@router.get("/invoices")
def list_invoices(account: Account, db: DB, status: str | None = None) -> list[dict[str, Any]]:
    q = select(Invoice).order_by(Invoice.created_at.desc()).limit(300)
    if status:
        q = q.where(Invoice.status == status)
    return [service.invoice_dict(db, i) for i in db.scalars(q)]


@router.get("/documents/{doc_id}")
def download(doc_id: uuid.UUID, account: Account, db: DB, download: bool = False) -> Response:
    doc = db.get(Document, doc_id)
    if doc is None:
        raise HTTPException(404, detail={"code": "not_found", "message": "File not found."})
    disposition = "attachment" if download else "inline"
    return Response(
        storage.read(doc),
        media_type=doc.content_type,
        headers={
            "content-disposition": f"{disposition}; filename*=UTF-8''{urlquote(doc.filename)}",
            "x-content-type-options": "nosniff",
            "cache-control": "private, no-store",
        },
    )
