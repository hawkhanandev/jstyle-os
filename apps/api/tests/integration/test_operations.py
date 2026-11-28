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
from app.modules.pricing.service import ensure_defaults
from app.modules.scheduling import service as scheduling
from app.modules.scheduling.models import ScheduledEmail
from app.worker.handlers import Deps
from app.worker.runner import run_event

TODAY = date.today()


@pytest.fixture(autouse=True)
def tmp_storage(tmp_path: Path) -> Iterator[None]:
    set_storage(LocalStorage(str(tmp_path)))
    yield
    set_storage(None)


def make_enquiry(db: Session, wedding: date) -> Enquiry:
    ensure_defaults(db, SYSTEM)
    templates.ensure_defaults(db, SYSTEM)
    e = create_enquiry(
        db,
        EnquiryInput(
            EnquiryType.BRIDE,
            "Kailani Akana",
            "kailani@example.com",
            wedding_date=wedding,
            region="HI",
            venue_name="Kualoa Ranch",
            venue_address="Kaneohe HI 96744",
            attendant_hair_count=2,
            attendant_makeup_count=2,
        ),
        SYSTEM,
        today=TODAY,
    )
    transition(db, e, Pipeline.UNDER_REVIEW, SYSTEM)
    db.flush()
    return e


def work(db: Session, mailer: RecordingMailer | None = None) -> list[str]:
    deps = Deps(
        settings=Settings(allowed_email="j@jstyle.example"), mailer=mailer or RecordingMailer()
    )
    return [run_event(db, ev.id, deps) for ev in outbox.claim_due(db)]


def book(authed: TestClient, db: Session, e: Enquiry) -> None:
    q = authed.post(f"/api/enquiries/{e.id}/quotes", json={"stylists_required": 1}).json()
    r = authed.post(
        f"/api/quotes/{q['id']}/submit",
        json={"acknowledged_flags": [*q["review_flags"], *e.needs_review_flags]},
    )
    assert r.status_code == 200, r.text
    authed.post(f"/api/quotes/{q['id']}/approve")
    work(db)
    authed.post(f"/api/quotes/{q['id']}/accept")
    authed.post(f"/api/enquiries/{e.id}/contract/prepare")
    p = authed.post(f"/api/enquiries/{e.id}/contract/send").json()
    work(db)
    authed.post(
        f"/api/contracts/{p['contracts'][0]['id']}/mark-signed",
        data={"signed_on": TODAY.isoformat(), "method": "pdf"},
    )
    authed.post(
        f"/api/enquiries/{e.id}/payments",
        json={
            "method": "venmo",
            "amount_cents": 10000,
            "received_on": TODAY.isoformat(),
            "verify": True,
        },
    )
    db.refresh(e)
    assert e.pipeline_status == "BOOKED"
    work(db)  # booking confirmation


def scheduled(db: Session) -> dict[str, ScheduledEmail]:
    rows = db.scalars(select(ScheduledEmail).where(ScheduledEmail.status == "scheduled"))
    return {r.kind: r for r in rows}


def test_booking_schedules_every_wedding_email(authed: TestClient, db: Session) -> None:
    e = make_enquiry(db, TODAY + timedelta(days=60))
    book(authed, db, e)
    s = scheduled(db)
    assert set(s) == {"prep_guide", "balance_reminder", "final_timeline", "thank_you_review"}
    hst = scheduling.ZoneInfo("Pacific/Honolulu")
    assert s["prep_guide"].send_at.astimezone(hst).date() == e.wedding_date - timedelta(days=14)
    assert s["thank_you_review"].send_at.astimezone(hst).hour == 10

    # Moving the wedding moves every email.
    new_day = TODAY + timedelta(days=90)
    authed.patch(f"/api/enquiries/{e.id}", json={"wedding_date": new_day.isoformat()})
    s = scheduled(db)
    assert s["prep_guide"].send_at.astimezone(hst).date() == new_day - timedelta(days=14)


def test_last_minute_booking_sends_prep_guide_now(authed: TestClient, db: Session) -> None:
    e = make_enquiry(db, TODAY + timedelta(days=4))
    book(authed, db, e)
    s = scheduled(db)
    assert s["prep_guide"].send_at <= datetime.now(UTC)
    assert scheduling.dispatch_due(db) == ["queued", "queued"]  # prep guide and balance
    mailer = RecordingMailer()
    assert sorted(work(db, mailer)) == ["done", "done"]
    subjects = sorted(m.subject for m in mailer.sent)
    assert subjects == ["Your remaining balance of $800", "Your wedding preparation guide"]
    names = sorted(a.filename for m in mailer.sent for a in m.attachments)
    assert names[0].startswith("Jstyle invoice JS-") and "preparation guide" in names[1]
    inv = authed.get(f"/api/enquiries/{e.id}/paperwork").json()["invoices"]
    assert {i["kind"]: i["status"] for i in inv} == {"deposit": "paid", "balance": "issued"}


def test_final_timeline_waits_for_full_payment(authed: TestClient, db: Session) -> None:
    e = make_enquiry(db, TODAY + timedelta(days=40))
    book(authed, db, e)
    ops = authed.get(f"/api/enquiries/{e.id}/operations").json()
    assert ops["final_timeline_blockers"] == ["Balance not paid in full", "No timeline entered"]
    r = authed.post(f"/api/enquiries/{e.id}/final-timeline/send")
    assert r.status_code == 409

    # Scheduled attempt while unpaid: skipped, and a task explains why.
    s = scheduled(db)["final_timeline"]
    assert "skipped" in scheduling.dispatch_due(db, now=s.send_at)
    assert db.scalar(select(Task).where(Task.kind == "final_timeline_blocked")) is not None

    authed.put(
        f"/api/enquiries/{e.id}/plan",
        json={
            "getting_ready_address": "Room 12, Kahala Hotel",
            "timeline": [
                {"time": "09:00", "person": "Maid of honour", "service": "Hair", "stylist": "J"},
                {
                    "time": "07:30",
                    "person": "Bride",
                    "service": "Hair and makeup",
                    "stylist": "Jessica",
                },
            ],
        },
    )
    authed.post(
        f"/api/enquiries/{e.id}/payments",
        json={
            "method": "zelle",
            "amount_cents": 80000,
            "received_on": TODAY.isoformat(),
            "verify": True,
        },
    )
    ops = authed.get(f"/api/enquiries/{e.id}/operations").json()
    assert ops["final_timeline_blockers"] == [] and ops["outstanding_cents"] == 0
    assert ops["plan"]["timeline"][0]["person"] == "Bride"  # sorted by time
    assert authed.post(f"/api/enquiries/{e.id}/final-timeline/send").status_code == 202
    mailer = RecordingMailer()
    assert "done" in work(db, mailer)
    tl = next(m for m in mailer.sent if m.subject.startswith("Your final timeline"))
    assert tl.attachments[0].filename.startswith("Jstyle final timeline")
    assert authed.get(f"/api/enquiries/{e.id}/operations").json()["plan"]["final_timeline_sent_at"]


def test_trial_reminder_two_days_before(authed: TestClient, db: Session) -> None:
    e = make_enquiry(db, TODAY + timedelta(days=60))
    book(authed, db, e)
    start = datetime.now(UTC) + timedelta(days=20)
    r = authed.post(
        f"/api/enquiries/{e.id}/trials",
        json={"starts_at": start.isoformat(), "location": "the studio"},
    )
    assert r.status_code == 201
    trial = r.json()["trials"][0]
    s = scheduled(db)["trial_reminder"]
    assert scheduling.dispatch_due(db, now=s.send_at) == ["queued"]
    mailer = RecordingMailer()
    work(db, mailer)
    assert "the studio" in mailer.sent[-1].html

    # Cancelling the trial cancels the reminder.
    authed.put(
        f"/api/enquiries/{e.id}/trials/{trial['id']}",
        json={"starts_at": (start + timedelta(days=3)).isoformat(), "status": "cancelled"},
    )
    assert "trial_reminder" not in scheduled(db)


def test_calendar_and_dashboard(authed: TestClient, db: Session) -> None:
    e = make_enquiry(db, TODAY + timedelta(days=30))
    book(authed, db, e)
    authed.post(
        f"/api/enquiries/{e.id}/trials",
        json={"starts_at": (datetime.now(UTC) + timedelta(days=10)).isoformat()},
    )
    ev = authed.get(
        f"/api/calendar?start={TODAY.isoformat()}&end={(TODAY + timedelta(days=60)).isoformat()}"
    ).json()
    assert sorted(x["type"] for x in ev) == ["trial", "wedding"]
    d: dict[str, Any] = authed.get("/api/dashboard").json()
    assert d["counts"]["outstanding_balances_cents"] == 80000
    assert d["upcoming_weddings"][0]["client_name"] == "Kailani Akana"
