from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.modules.documents.storage import LocalStorage, set_storage
from app.modules.email import templates
from app.modules.email.mailer import RecordingMailer
from app.modules.enquiries.models import Enquiry, EnquiryType, Pipeline, Task
from app.modules.enquiries.pipeline import transition
from app.modules.enquiries.service import EnquiryInput, create_enquiry
from app.modules.platform import outbox
from app.modules.platform.audit import SYSTEM
from app.modules.platform.models import OutboxEvent
from app.modules.pricing.service import ensure_defaults
from app.modules.scheduling import service as scheduling
from app.modules.scheduling.models import ScheduledEmail
from app.worker.handlers import Deps
from app.worker.runner import run_event


@pytest.fixture(autouse=True)
def tmp_storage(tmp_path: Path) -> Iterator[None]:
    set_storage(LocalStorage(str(tmp_path)))
    yield
    set_storage(None)


@pytest.fixture
def enquiry(db: Session) -> Enquiry:
    ensure_defaults(db, SYSTEM)
    templates.ensure_defaults(db, SYSTEM)
    e = create_enquiry(
        db,
        EnquiryInput(
            EnquiryType.BRIDE,
            "Kailani Akana",
            "kailani@example.com",
            wedding_date=date(2027, 6, 12),
            region="HI",
            venue_address="Kaneohe HI 96744",
            attendant_hair_count=2,
            attendant_makeup_count=2,
        ),
        SYSTEM,
        today=date(2026, 12, 1),
    )
    transition(db, e, Pipeline.UNDER_REVIEW, SYSTEM)
    db.flush()
    return e


def work(db: Session, mailer: RecordingMailer | None = None) -> list[str]:
    deps = Deps(
        settings=Settings(allowed_email="j@jstyle.example"), mailer=mailer or RecordingMailer()
    )
    return [run_event(db, ev.id, deps) for ev in outbox.claim_due(db)]


def send_quote(authed: TestClient, db: Session, e: Enquiry) -> dict[str, Any]:
    q = authed.post(f"/api/enquiries/{e.id}/quotes", json={"stylists_required": 1}).json()
    authed.post(f"/api/quotes/{q['id']}/submit", json={"acknowledged_flags": q["review_flags"]})
    authed.post(f"/api/quotes/{q['id']}/approve")
    assert work(db) == ["done"]
    return q


def test_local_time_conversion() -> None:
    assert scheduling.local_at(date(2027, 1, 5), "Pacific/Honolulu") == datetime(
        2027, 1, 5, 20, 0, tzinfo=UTC
    )
    # Oregon in summer is UTC-7.
    assert scheduling.local_at(date(2027, 7, 5), "America/Los_Angeles") == datetime(
        2027, 7, 5, 17, 0, tzinfo=UTC
    )


def test_follow_up_is_sent_at_10am_local_five_days_later(
    authed: TestClient, db: Session, enquiry: Enquiry
) -> None:
    send_quote(authed, db, enquiry)
    s = db.scalar(select(ScheduledEmail))
    assert s is not None and s.kind == "quote_follow_up"
    local = s.send_at.astimezone(scheduling.ZoneInfo("Pacific/Honolulu"))
    assert local.hour == 10
    assert scheduling.dispatch_due(db, now=s.send_at - timedelta(minutes=1)) == []
    assert scheduling.dispatch_due(db, now=s.send_at) == ["queued"]
    mailer = RecordingMailer()
    assert work(db, mailer) == ["done"]
    assert "quote" in mailer.sent[0].subject.lower() or mailer.sent[0].subject
    assert scheduling.dispatch_due(db, now=s.send_at + timedelta(days=1)) == []  # only once


def test_follow_up_skipped_when_client_replied(
    authed: TestClient, db: Session, enquiry: Enquiry
) -> None:
    send_quote(authed, db, enquiry)
    authed.post(f"/api/dev/enquiries/{enquiry.id}/simulate-reply", json={"body": "Thinking!"})
    s = db.scalar(select(ScheduledEmail))
    assert s is not None
    assert scheduling.dispatch_due(db, now=s.send_at) == ["skipped"]
    assert s.note == "client replied"


def test_revision_replaces_follow_up(authed: TestClient, db: Session, enquiry: Enquiry) -> None:
    send_quote(authed, db, enquiry)
    transition(db, enquiry, Pipeline.DISCUSSION_REVISION, SYSTEM)
    q2 = authed.post(
        f"/api/enquiries/{enquiry.id}/quotes", json={"attendant_hair": 3, "stylists_required": 1}
    ).json()
    r = authed.post(
        f"/api/quotes/{q2['id']}/submit", json={"acknowledged_flags": q2["review_flags"]}
    )
    assert r.status_code == 200, r.text
    assert authed.post(f"/api/quotes/{q2['id']}/approve").status_code == 200
    assert work(db) == ["done"]
    rows = db.scalars(select(ScheduledEmail).order_by(ScheduledEmail.created_at)).all()
    assert [r.status for r in rows] == ["cancelled", "scheduled"]
    assert str(rows[1].ref_id) == q2["id"]


def test_cancel_wedding_stops_everything(authed: TestClient, db: Session, enquiry: Enquiry) -> None:
    q = send_quote(authed, db, enquiry)
    authed.post(f"/api/quotes/{q['id']}/accept")
    authed.post(f"/api/enquiries/{enquiry.id}/contract/prepare")
    authed.post(f"/api/enquiries/{enquiry.id}/contract/send")  # queued, not yet sent
    scheduling.schedule(
        db, enquiry, "balance_reminder", "balance_reminder", datetime.now(UTC) + timedelta(days=9)
    )
    r = authed.post(f"/api/enquiries/{enquiry.id}/cancel-wedding", json={"reason": "Postponed"})
    assert r.status_code == 200, r.text
    assert r.json() == {"invoices_voided": 1, "scheduled_cancelled": 1, "queued_stopped": 1}
    db.refresh(enquiry)
    assert enquiry.pipeline_status == "CANCELLED"
    assert work(db) == []
    ev = db.scalar(select(OutboxEvent).where(OutboxEvent.kind == "booking.send_contract"))
    assert ev is not None and ev.status == "dead"
    assert {
        s["status"] for s in authed.get(f"/api/enquiries/{enquiry.id}/scheduled-emails").json()
    } == {"cancelled"}


def test_overdue_deposit_raises_one_task(authed: TestClient, db: Session, enquiry: Enquiry) -> None:
    q = send_quote(authed, db, enquiry)
    authed.post(f"/api/quotes/{q['id']}/accept")
    authed.post(f"/api/enquiries/{enquiry.id}/contract/prepare")
    authed.post(f"/api/enquiries/{enquiry.id}/contract/send")
    work(db)
    later = date.today() + timedelta(days=30)
    assert scheduling.daily_checks(db, later) == 1
    assert scheduling.daily_checks(db, later) == 0
    t = db.scalar(select(Task).where(Task.kind == "deposit_overdue"))
    assert t is not None and "Kailani" in t.title
