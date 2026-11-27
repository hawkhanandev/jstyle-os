from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.modules.auth.deps import Account
from app.modules.replies import service
from app.modules.replies.models import Intent, ReplySuggestion

router = APIRouter(tags=["replies"])
DB = Annotated[Session, Depends(get_session)]


def _get(db: Session, sid: uuid.UUID) -> ReplySuggestion:
    s = db.get(ReplySuggestion, sid)
    if s is None:
        raise HTTPException(404, detail={"code": "not_found", "message": "Reply not found."})
    return s


@router.get("/replies")
def list_pending(
    account: Account, db: DB, enquiry_id: uuid.UUID | None = None
) -> list[dict[str, Any]]:
    return [service.to_dict(db, s) for s in service.pending(db, enquiry_id)]


class ConfirmIn(BaseModel):
    intent: Intent


@router.post("/replies/{sid}/confirm")
def confirm(sid: uuid.UUID, body: ConfirmIn, account: Account, db: DB) -> dict[str, Any]:
    s = _get(db, sid)
    try:
        service.confirm(db, s, body.intent, account.actor)
    except service.ReplyError as exc:
        db.rollback()
        raise HTTPException(409, detail={"code": exc.code, "message": str(exc)}) from exc
    db.commit()
    return service.to_dict(db, s)


@router.post("/replies/{sid}/dismiss")
def dismiss(sid: uuid.UUID, account: Account, db: DB) -> dict[str, Any]:
    s = _get(db, sid)
    try:
        service.dismiss(db, s, account.actor)
    except service.ReplyError as exc:
        raise HTTPException(409, detail={"code": exc.code, "message": str(exc)}) from exc
    db.commit()
    return service.to_dict(db, s)
