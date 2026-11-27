from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.modules.bookings.models import Booking
from app.modules.email import templates
from app.modules.email.mailer import RecordingMailer
from app.modules.enquiries.models import Enquiry, EnquiryType, Pipeline
from app.modules.enquiries.pipeline import transition
from app.modules.enquiries.service import EnquiryInput, create_enquiry
from app.modules.platform import outbox
from app.modules.platform.audit import SYSTEM
from app.modules.pricing.service import ensure_defaults
from app.modules.quotes.models import Quote
from app.modules.replies.models import ReplySuggestion
from app.worker.handlers import Deps
from app.worker.runner import run_event


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


def work(db: Session) -> list[str]:
    deps = Deps(settings=Settings(allowed_email="j@jstyle.example"), mailer=RecordingMailer())
    return [run_event(db, ev.id, deps) for ev in outbox.claim_due(db)]


def sent_quote(authed: TestClient, db: Session, e: Enquiry, **inputs: Any) -> dict[str, Any]:
    q = authed.post(f"/api/enquiries/{e.id}/quotes", json=inputs).json()
    authed.post(f"/api/quotes/{q['id']}/submit", json={"acknowledged_flags": q["review_flags"]})
    authed.post(f"/api/quotes/{q['id']}/approve")
    assert work(db) == ["done"]
    return q


def client_says(authed: TestClient, e: Enquiry, body: str) -> dict[str, Any]:
    r = authed.post(f"/api/dev/enquiries/{e.id}/simulate-reply", json={"body": body})
    assert r.status_code == 201
    pending = authed.get(f"/api/replies?enquiry_id={e.id}").json()
    return pending[-1] if pending else {}


def test_acceptance_needs_a_staff_click(authed: TestClient, db: Session, enquiry: Enquiry) -> None:
    q = sent_quote(authed, db, enquiry, stylists_required=1)
    s = client_says(authed, enquiry, "We'd love to book! How do we pay the deposit?")
    assert s["intent"] == "accept" and s["confidence"] == "high"
    db.refresh(enquiry)
    assert enquiry.pipeline_status == "QUOTE_SENT"  # nothing changes on its own
    assert db.scalar(select(Booking)) is None

    r = authed.post(f"/api/replies/{s['id']}/confirm", json={"intent": "accept"})
    assert r.status_code == 200 and r.json()["status"] == "confirmed"
    db.refresh(enquiry)
    assert enquiry.pipeline_status == "QUOTE_ACCEPTED"
    assert db.get(Quote, q["id"]).status == "accepted"  # type: ignore[union-attr]

    b = authed.get(f"/api/enquiries/{enquiry.id}/booking").json()
    assert b["total_cents"] == 90000 and b["deposit_cents"] == 10000
    assert b["stylists_required"] == 1 and b["quote_version"] == 1
    assert b["missing"] == ["contract_signed", "deposit_verified"]
    assert [i["done"] for i in b["checklist"]] == [True, False, False, False, True]
    assert authed.get("/api/replies").json() == []


def test_staff_can_correct_the_suggestion(
    authed: TestClient, db: Session, enquiry: Enquiry
) -> None:
    sent_quote(authed, db, enquiry, stylists_required=1)
    s = client_says(authed, enquiry, "Sounds great! Could we add makeup for my mom?")
    assert s["intent"] == "change_request"
    authed.post(f"/api/replies/{s['id']}/confirm", json={"intent": "change_request"})
    db.refresh(enquiry)
    assert enquiry.pipeline_status == "DISCUSSION_REVISION"

    s2 = client_says(authed, enquiry, "Thank you!")
    assert s2["intent"] == "other"
    assert authed.post(f"/api/replies/{s2['id']}/dismiss").json()["status"] == "dismissed"
    again = authed.post(f"/api/replies/{s2['id']}/dismiss")
    assert again.status_code == 409


def test_decline_closes_and_withdraws_open_revision(
    authed: TestClient, db: Session, enquiry: Enquiry
) -> None:
    sent_quote(authed, db, enquiry, stylists_required=1)
    draft = authed.post(f"/api/enquiries/{enquiry.id}/quotes", json={"attendant_hair": 3}).json()
    s = client_says(authed, enquiry, "Thanks but we decided to go with another artist.")
    assert s["intent"] == "decline"
    authed.post(f"/api/replies/{s['id']}/confirm", json={"intent": "decline"})
    db.refresh(enquiry)
    assert enquiry.pipeline_status == "LOST_DECLINED"
    assert db.get(Quote, draft["id"]).status == "withdrawn"  # type: ignore[union-attr]


def test_accept_blocked_while_revision_open(
    authed: TestClient, db: Session, enquiry: Enquiry
) -> None:
    q = sent_quote(authed, db, enquiry, stylists_required=1)
    authed.post(f"/api/enquiries/{enquiry.id}/quotes", json={})
    r = authed.post(f"/api/quotes/{q['id']}/accept")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "revision_open"


def test_staff_acceptance_and_stylists(authed: TestClient, db: Session, enquiry: Enquiry) -> None:
    q = sent_quote(authed, db, enquiry, travel_zone="in_town")
    b = authed.post(f"/api/quotes/{q['id']}/accept").json()
    assert "stylists_required" in b["missing"]
    b = authed.patch(f"/api/enquiries/{enquiry.id}/booking", json={"stylists_required": 2}).json()
    assert b["stylists_required"] == 2 and "stylists_required" not in b["missing"]
    assert authed.post(f"/api/quotes/{q['id']}/accept").status_code == 409


def test_no_suggestion_without_a_sent_quote(
    authed: TestClient, db: Session, enquiry: Enquiry
) -> None:
    outbox.enqueue(
        db,
        "email.send",
        f"ack:{enquiry.id}",
        {"enquiry_id": str(enquiry.id), "template": "enquiry_ack"},
    )
    work(db)
    client_says(authed, enquiry, "We'd love to book!")
    assert db.scalar(select(ReplySuggestion)) is None
