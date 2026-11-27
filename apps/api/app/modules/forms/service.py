from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.db import utcnow
from app.modules.enquiries.models import Enquiry
from app.modules.enquiries.region import detect_region
from app.modules.enquiries.service import create_enquiry, find_duplicate
from app.modules.forms import spam
from app.modules.forms.models import FormSubmission, SubmissionStatus
from app.modules.forms.schemas import BrideForm, PlannerForm
from app.modules.forms.verifiers import MailCheck, Turnstile
from app.modules.platform import outbox
from app.modules.platform.audit import SYSTEM, Actor, write_audit

IP_PER_HOUR = 5
EMAIL_PER_DAY = 3


@dataclass(frozen=True)
class Outcome:
    status: SubmissionStatus
    submission_id: uuid.UUID
    enquiry_id: uuid.UUID | None = None
    http_status: int = 200


def _queue_acknowledgement(db: Session, enquiry: Enquiry) -> None:
    outbox.enqueue(
        db,
        "email.send",
        f"enquiry_ack:{enquiry.id}",
        {"template": "enquiry_ack", "enquiry_id": str(enquiry.id)},
        aggregate_type="enquiry",
        aggregate_id=enquiry.id,
    )


def _accept(
    db: Session, form: BrideForm | PlannerForm, sub: FormSubmission, actor: Actor, today: date
) -> None:
    data = form.to_input()
    dup = find_duplicate(db, data.email, data.wedding_date, today=today)
    if dup is not None:
        stamp = utcnow().strftime("%Y-%m-%d %H:%M UTC")
        extra = data.notes or "(no new notes)"
        dup.notes = f"{dup.notes or ''}\n\n[Form submitted again {stamp}] {extra}".strip()
        write_audit(
            db,
            actor,
            "enquiry.duplicate_merged",
            entity_type="enquiry",
            entity_id=dup.id,
            after={"submission_id": str(sub.id)},
        )
        sub.status = SubmissionStatus.MERGED
        sub.enquiry_id = dup.id
        return
    enquiry = create_enquiry(db, data, actor, today=today)
    sub.enquiry_id = enquiry.id
    _queue_acknowledgement(db, enquiry)


def submit(
    db: Session,
    settings: Settings,
    form: BrideForm | PlannerForm,
    *,
    ip: str | None,
    user_agent: str | None,
    turnstile: Turnstile,
    mail_check: MailCheck,
    today: date,
    now_ts: float | None = None,
) -> Outcome:
    kind = "bride" if isinstance(form, BrideForm) else "planner"
    email = str(form.email).lower()
    ip_hash = spam.hash_ip(settings.secret_key, ip)
    sub = FormSubmission(
        form=kind,
        payload=form.model_dump(mode="json", exclude={"turnstile_token"}),
        email=email,
        ip_hash=ip_hash,
        user_agent=user_agent,
        spam_score=0,
        spam_reasons=[],
        status=SubmissionStatus.ACCEPTED,
    )
    db.add(sub)

    def finish(status: SubmissionStatus, http_status: int = 200) -> Outcome:
        sub.status = status
        db.flush()
        db.commit()
        return Outcome(status, sub.id, sub.enquiry_id, http_status)

    # 1. Turnstile (hard reject)
    sub.turnstile_ok = turnstile.verify(form.turnstile_token, ip)
    if not sub.turnstile_ok:
        sub.spam_reasons = ["turnstile_failed"]
        return finish(SubmissionStatus.REJECTED, 400)

    # 3. Rate limits (hard reject). Counted from the log, so they survive restarts.
    hour_ago, day_ago = utcnow() - timedelta(hours=1), utcnow() - timedelta(days=1)
    if ip_hash:
        by_ip = db.scalar(
            select(func.count())
            .select_from(FormSubmission)
            .where(FormSubmission.ip_hash == ip_hash, FormSubmission.created_at >= hour_ago)
        )
        if (by_ip or 0) >= IP_PER_HOUR:
            sub.spam_reasons = ["rate_limited_ip"]
            return finish(SubmissionStatus.REJECTED, 429)
    by_email = db.scalar(
        select(func.count())
        .select_from(FormSubmission)
        .where(FormSubmission.email == email, FormSubmission.created_at >= day_ago)
    )
    if (by_email or 0) >= EMAIL_PER_DAY:
        sub.spam_reasons = ["rate_limited_email"]
        return finish(SubmissionStatus.REJECTED, 429)

    # 2. Honeypot and timing (hold)
    verdict = spam.Verdict()
    if form.website:
        verdict.add(100, "honeypot")
    elapsed = spam.fill_seconds(settings.secret_key, form.form_token, now_ts)
    sub.fill_seconds = elapsed
    if elapsed is None:
        verdict.add(60, "missing_form_token")
    elif elapsed < spam.MIN_FILL_SECONDS:
        verdict.add(60, "too_fast")
    elif elapsed > spam.MAX_FILL_SECONDS:
        verdict.add(60, "form_too_old")

    # 4. Content scoring (hold at 50+)
    data = form.to_input()
    content = spam.score_content(
        email=email,
        phone=data.phone,
        wedding_date=data.wedding_date,
        region_known=detect_region(data.region, data.venue_address, data.venue_name) is not None,
        free_text=[
            data.notes,
            data.travel_notes,
            data.venue_name,
            (data.services or {}).get("services_needed"),
        ],
        today=today,
        has_mail_server=mail_check.has_mail_server(email.rsplit("@", 1)[-1]),
    )
    sub.spam_score = verdict.score + content.score
    sub.spam_reasons = verdict.reasons + content.reasons
    if sub.spam_score >= spam.HOLD_THRESHOLD:
        return finish(SubmissionStatus.HELD)

    # 5. Duplicate merge, else a new enquiry plus acknowledgement
    db.flush()
    _accept(db, form, sub, SYSTEM, today)
    return finish(SubmissionStatus(sub.status))


def parse_payload(kind: str, payload: dict[str, Any]) -> BrideForm | PlannerForm:
    return (BrideForm if kind == "bride" else PlannerForm).model_validate(payload)


def approve(db: Session, sub: FormSubmission, actor: Actor, today: date) -> FormSubmission:
    if sub.status != SubmissionStatus.HELD:
        raise ValueError("only held submissions can be approved")
    _accept(db, parse_payload(sub.form, sub.payload), sub, actor, today)
    if sub.status != SubmissionStatus.MERGED:
        sub.status = SubmissionStatus.APPROVED
    write_audit(
        db,
        actor,
        "form_submission.approve",
        entity_type="form_submission",
        entity_id=sub.id,
        after={"enquiry_id": str(sub.enquiry_id)},
    )
    return sub


def delete(db: Session, sub: FormSubmission, actor: Actor) -> FormSubmission:
    if sub.status != SubmissionStatus.HELD:
        raise ValueError("only held submissions can be deleted")
    sub.status = SubmissionStatus.DELETED
    write_audit(
        db, actor, "form_submission.delete", entity_type="form_submission", entity_id=sub.id
    )
    return sub


def today_counts(db: Session) -> dict[str, int]:
    start = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    rows = db.execute(
        select(FormSubmission.status, func.count())
        .where(FormSubmission.created_at >= start)
        .group_by(FormSubmission.status)
    ).all()
    counts = {s.value: 0 for s in SubmissionStatus}
    counts.update({status: n for status, n in rows})
    counts["held_total"] = (
        db.scalar(
            select(func.count())
            .select_from(FormSubmission)
            .where(FormSubmission.status == SubmissionStatus.HELD)
        )
        or 0
    )
    return counts
