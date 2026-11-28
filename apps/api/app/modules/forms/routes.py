from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.db import get_session
from app.modules.auth.deps import Account, client_ip
from app.modules.forms import layout, service, spam
from app.modules.forms.models import FormSubmission, SubmissionStatus
from app.modules.forms.schemas import BrideForm, PlannerForm
from app.modules.forms.verifiers import MailCheck, Turnstile, get_mail_check, get_turnstile

public = APIRouter(prefix="/public", tags=["public forms"])
staff = APIRouter(prefix="/form-submissions", tags=["forms"])
layouts = APIRouter(prefix="/form-layouts", tags=["forms"])

DB = Annotated[Session, Depends(get_session)]
Cfg = Annotated[Settings, Depends(get_settings)]
TS = Annotated[Turnstile, Depends(get_turnstile)]
MX = Annotated[MailCheck, Depends(get_mail_check)]

MESSAGES = {
    400: "We couldn't verify the form. Please reload the page and try again.",
    429: "We've received several submissions already. Please try again later or email us.",
}


@public.get("/forms/config")
def form_config(settings: Cfg, db: DB, kind: layout.Kind | None = None) -> dict[str, Any]:
    """Called when the form loads: a signed start time, the Turnstile key and the form layout."""
    out: dict[str, Any] = {
        "form_token": spam.issue_form_token(settings.secret_key),
        "turnstile_site_key": settings.turnstile_site_key,
    }
    if kind:
        out["layout"] = layout.public_view(kind, layout.get_layout(db, kind))
    return out


def _apply_layout(
    db: Session, kind: layout.Kind, form: BrideForm | PlannerForm
) -> JSONResponse | None:
    """Check required fields from the editable layout; attach custom answers to the form."""
    values = form.model_dump(exclude={"custom", "custom_answers"})
    try:
        form.custom_answers = layout.check_answers(
            kind, layout.get_layout(db, kind), values, form.custom
        )
    except layout.MissingAnswers as exc:
        return JSONResponse(
            {"ok": False, "message": f"Please fill in: {', '.join(exc.labels)}."}, status_code=422
        )
    return None


def _respond(outcome: service.Outcome) -> JSONResponse:
    if outcome.http_status != 200:
        return JSONResponse(
            {"ok": False, "message": MESSAGES[outcome.http_status]}, status_code=outcome.http_status
        )
    # Held submissions get the same thank-you, so spammers learn nothing.
    return JSONResponse({"ok": True, "message": "Thank you! We'll be in touch within 2 days."})


@public.post("/enquiries/bride")
def submit_bride(
    form: BrideForm, request: Request, db: DB, settings: Cfg, turnstile: TS, mail: MX
) -> JSONResponse:
    if (bad := _apply_layout(db, "bride", form)) is not None:
        return bad
    return _respond(
        service.submit(
            db,
            settings,
            form,
            ip=client_ip(request),
            user_agent=request.headers.get("user-agent"),
            turnstile=turnstile,
            mail_check=mail,
            today=date.today(),
        )
    )


@public.post("/enquiries/planner")
def submit_planner(
    form: PlannerForm, request: Request, db: DB, settings: Cfg, turnstile: TS, mail: MX
) -> JSONResponse:
    if (bad := _apply_layout(db, "planner", form)) is not None:
        return bad
    return _respond(
        service.submit(
            db,
            settings,
            form,
            ip=client_ip(request),
            user_agent=request.headers.get("user-agent"),
            turnstile=turnstile,
            mail_check=mail,
            today=date.today(),
        )
    )


class SubmissionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    form: str
    email: str | None
    payload: dict[str, Any]
    spam_score: int
    spam_reasons: list[str]
    fill_seconds: float | None
    status: str
    enquiry_id: uuid.UUID | None
    created_at: datetime


@staff.get("")
def list_submissions(
    account: Account, db: DB, status: SubmissionStatus = SubmissionStatus.HELD
) -> list[SubmissionOut]:
    rows = db.scalars(
        select(FormSubmission)
        .where(FormSubmission.status == status)
        .order_by(FormSubmission.created_at.desc())
        .limit(200)
    )
    return [SubmissionOut.model_validate(r) for r in rows]


@staff.get("/stats")
def stats(account: Account, db: DB) -> dict[str, int]:
    return service.today_counts(db)


def _held(db: Session, sub_id: uuid.UUID) -> FormSubmission:
    sub = db.get(FormSubmission, sub_id)
    if sub is None or sub.status != SubmissionStatus.HELD:
        raise HTTPException(
            404, detail={"code": "not_found", "message": "No held submission with that id."}
        )
    return sub


@staff.post("/{sub_id}/approve")
def approve(sub_id: uuid.UUID, account: Account, db: DB) -> SubmissionOut:
    sub = service.approve(db, _held(db, sub_id), account.actor, date.today())
    db.commit()
    return SubmissionOut.model_validate(sub)


@staff.post("/{sub_id}/delete")
def delete(sub_id: uuid.UUID, account: Account, db: DB) -> SubmissionOut:
    sub = service.delete(db, _held(db, sub_id), account.actor)
    db.commit()
    return SubmissionOut.model_validate(sub)


@layouts.get("/{kind}")
def get_form_layout(kind: layout.Kind, account: Account, db: DB) -> dict[str, Any]:
    return layout.editor_view(kind, layout.get_layout(db, kind))


@layouts.put("/{kind}")
def put_form_layout(
    kind: layout.Kind, body: layout.FormLayout, account: Account, db: DB
) -> dict[str, Any]:
    try:
        saved = layout.save_layout(db, kind, body, account.actor)
    except ValueError as exc:
        raise HTTPException(422, detail={"code": "invalid", "message": str(exc)}) from exc
    db.commit()
    return layout.editor_view(kind, saved)


@layouts.post("/{kind}/reset")
def reset_form_layout(kind: layout.Kind, account: Account, db: DB) -> dict[str, Any]:
    saved = layout.save_layout(db, kind, layout.default_layout(kind), account.actor)
    db.commit()
    return layout.editor_view(kind, saved)
