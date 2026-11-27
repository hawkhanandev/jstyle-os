from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.modules.email import templates
from app.modules.email.mailer import OutgoingMail, RecordingMailer, SentMail
from app.modules.email.models import EmailMessage
from app.modules.enquiries.models import Enquiry, EnquiryType, Pipeline
from app.modules.enquiries.pipeline import transition
from app.modules.enquiries.service import EnquiryInput, create_enquiry
from app.modules.platform import outbox
from app.modules.platform.audit import SYSTEM
from app.modules.platform.models import OutboxEvent
from app.modules.pricing.rate_cards import RateCard
from app.modules.pricing.service import create_version, ensure_defaults
from app.modules.pricing.types import Region
from app.modules.quotes.models import Quote
from app.worker.handlers import Deps
from app.worker.runner import run_event

TODAY = date(2026, 12, 1)


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


def work(db: Session, mailer: Any = None) -> list[str]:
    deps = Deps(
        settings=Settings(allowed_email="jessica@jstyle.example"),
        mailer=mailer or RecordingMailer(),
    )
    return [run_event(db, e.id, deps) for e in outbox.claim_due(db)]


def send_flow(authed: TestClient, enquiry_id: Any, **inputs: Any) -> dict[str, Any]:
    q = authed.post(f"/api/enquiries/{enquiry_id}/quotes", json=inputs).json()
    authed.post(f"/api/quotes/{q['id']}/submit", json={"acknowledged_flags": q["review_flags"]})
    return authed.post(f"/api/quotes/{q['id']}/approve").json()


def test_prd_hawaii_quote_end_to_end(authed: TestClient, db: Session, enquiry: Enquiry) -> None:
    # Outside venue with no stylist count: blocked until travel is confirmed
    q = authed.post(f"/api/enquiries/{enquiry.id}/quotes", json={}).json()
    assert q["status"] == "draft" and "travel_unconfirmed" in q["review_flags"]
    blocked = authed.post(f"/api/quotes/{q['id']}/submit", json={"acknowledged_flags": []})
    assert blocked.json()["detail"]["code"] == "travel_unconfirmed"

    q = authed.patch(f"/api/quotes/{q['id']}", json={"stylists_required": 1}).json()
    assert q["total_cents"] == 90_000 and q["deposit_cents"] == 10_000
    assert q["balance_cents"] == 80_000 and q["review_flags"] == []

    q = authed.post(f"/api/quotes/{q['id']}/submit", json={"acknowledged_flags": []}).json()
    assert q["status"] == "awaiting_approval"
    assert db.get(Enquiry, enquiry.id).pipeline_status == "AWAITING_APPROVAL"  # type: ignore[union-attr]

    q = authed.post(f"/api/quotes/{q['id']}/approve").json()
    assert q["status"] == "sending"
    assert "$900" in q["email_body_html"] and "$800" in q["email_body_html"]
    # Not QUOTE_SENT until the email has actually gone
    assert db.get(Enquiry, enquiry.id).pipeline_status == "AWAITING_APPROVAL"  # type: ignore[union-attr]

    mailer = RecordingMailer()
    assert work(db, mailer) == ["done"]
    sent = db.get(Quote, q["id"])
    assert sent.status == "sent" and sent.email_message_id is not None  # type: ignore[union-attr]
    assert db.get(Enquiry, enquiry.id).pipeline_status == "QUOTE_SENT"  # type: ignore[union-attr]
    assert mailer.sent[0].html == q["email_body_html"]  # exactly what was approved
    msg = db.get(EmailMessage, sent.email_message_id)  # type: ignore[union-attr]
    assert msg is not None and msg.body_html == q["email_body_html"]


def test_cannot_approve_without_submit(authed: TestClient, enquiry: Enquiry) -> None:
    q = authed.post(f"/api/enquiries/{enquiry.id}/quotes", json={"stylists_required": 1}).json()
    assert authed.post(f"/api/quotes/{q['id']}/approve").status_code == 409


def test_flags_must_be_acknowledged(authed: TestClient, enquiry: Enquiry) -> None:
    q = authed.post(
        f"/api/enquiries/{enquiry.id}/quotes",
        json={"stylists_required": 1, "bridal_package": "hair_only"},
    ).json()
    res = authed.post(f"/api/quotes/{q['id']}/submit", json={"acknowledged_flags": []})
    assert res.status_code == 409
    assert res.json()["detail"]["details"] == ["partial_bridal_package"]
    ok = authed.post(
        f"/api/quotes/{q['id']}/submit", json={"acknowledged_flags": ["partial_bridal_package"]}
    )
    assert ok.status_code == 200


class BrokenMailer:
    def send(self, mail: OutgoingMail) -> SentMail:
        from app.modules.platform.outbox import PermanentError

        raise PermanentError("invalid recipient")


def test_failed_send_leaves_pipeline_and_can_retry(
    authed: TestClient, db: Session, enquiry: Enquiry
) -> None:
    q = send_flow(authed, enquiry.id, stylists_required=1)
    assert work(db, BrokenMailer()) == ["failed"]
    quote = db.get(Quote, q["id"])
    assert quote.status == "send_failed" and "invalid recipient" in quote.send_error  # type: ignore[union-attr,operator]
    assert db.get(Enquiry, enquiry.id).pipeline_status == "AWAITING_APPROVAL"  # type: ignore[union-attr]

    retried = authed.post(f"/api/quotes/{q['id']}/retry-send").json()
    assert retried["status"] == "sending"
    assert work(db) == ["done"]
    assert db.get(Enquiry, enquiry.id).pipeline_status == "QUOTE_SENT"  # type: ignore[union-attr]


def test_revision_supersedes_and_keeps_v1(
    authed: TestClient, db: Session, enquiry: Enquiry
) -> None:
    v1 = send_flow(authed, enquiry.id, stylists_required=1)
    work(db)
    v2 = authed.post(
        f"/api/enquiries/{enquiry.id}/quotes", json={"stylists_required": 1, "attendant_hair": 3}
    ).json()
    assert v2["version"] == 2 and v2["supersedes_quote_id"] == v1["id"]
    assert db.get(Enquiry, enquiry.id).pipeline_status == "DISCUSSION_REVISION"  # type: ignore[union-attr]
    authed.post(f"/api/quotes/{v2['id']}/submit", json={"acknowledged_flags": []})
    approved = authed.post(f"/api/quotes/{v2['id']}/approve").json()
    assert (
        "updated quote" in approved["email_subject"].lower()
        or "updated" in approved["email_body_html"]
    )
    work(db)
    old, new = db.get(Quote, v1["id"]), db.get(Quote, v2["id"])
    assert old.status == "superseded" and old.total_cents == 90_000  # type: ignore[union-attr]
    assert new.status == "sent" and new.total_cents == 102_000  # type: ignore[union-attr]
    assert db.get(Enquiry, enquiry.id).pipeline_status == "QUOTE_SENT"  # type: ignore[union-attr]
    assert len(db.scalars(select(EmailMessage)).all()) == 2


def test_rate_change_does_not_touch_existing_quote(
    authed: TestClient, db: Session, enquiry: Enquiry
) -> None:
    q = authed.post(f"/api/enquiries/{enquiry.id}/quotes", json={"stylists_required": 1}).json()
    create_version(
        db,
        SYSTEM,
        RateCard(
            Region.HAWAII, 0, 40_000, 12_000, 13_000, 25_000, 10_000, travel_per_stylist_cents=7_500
        ),
    )
    db.flush()
    edited = authed.patch(f"/api/quotes/{q['id']}", json={"trial": False}).json()
    assert edited["total_cents"] == 90_000 and edited["rate_card_version"] == 1
    repriced = authed.post(f"/api/quotes/{q['id']}/reprice").json()
    assert repriced["total_cents"] == 97_500 and repriced["rate_card_version"] == 2


def test_reject_and_withdraw(authed: TestClient, db: Session, enquiry: Enquiry) -> None:
    q = authed.post(f"/api/enquiries/{enquiry.id}/quotes", json={"stylists_required": 1}).json()
    authed.post(f"/api/quotes/{q['id']}/submit", json={"acknowledged_flags": []})
    r = authed.post(f"/api/quotes/{q['id']}/reject", json={"note": "Add trial"}).json()
    assert r["status"] == "draft" and r["rejection_note"] == "Add trial"
    assert db.get(Enquiry, enquiry.id).pipeline_status == "QUOTE_DRAFT"  # type: ignore[union-attr]
    w = authed.post(f"/api/quotes/{q['id']}/withdraw", json={"note": "Client paused"}).json()
    assert w["status"] == "withdrawn"
    again = authed.post(f"/api/enquiries/{enquiry.id}/quotes", json={"stylists_required": 1})
    assert again.status_code == 201 and again.json()["version"] == 2


def test_approval_queue(authed: TestClient, enquiry: Enquiry) -> None:
    q = authed.post(f"/api/enquiries/{enquiry.id}/quotes", json={"stylists_required": 1}).json()
    authed.post(f"/api/quotes/{q['id']}/submit", json={"acknowledged_flags": []})
    queue = authed.get("/api/quotes").json()
    assert queue[0]["id"] == q["id"] and queue[0]["client_name"] == "Kailani Akana"


def test_preview_is_frozen_after_approval(
    authed: TestClient, db: Session, enquiry: Enquiry
) -> None:
    q = send_flow(authed, enquiry.id, stylists_required=1)
    templates.save_version(db, SYSTEM, "quote", "Quotation", "Changed", "<p>changed</p>")
    db.flush()
    preview = authed.get(f"/api/quotes/{q['id']}/preview-email").json()
    assert preview["frozen"] == "true" and preview["html"] == q["email_body_html"]
    assert db.scalars(select(OutboxEvent)).first() is not None
