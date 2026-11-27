from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.modules.email import templates
from app.modules.email.mailer import RecordingMailer
from app.modules.email.models import EmailMessage, EmailThread
from app.modules.enquiries.models import Enquiry, EnquiryType
from app.modules.enquiries.service import EnquiryInput, create_enquiry
from app.modules.inbox.service import InboundMail, ingest_inbound
from app.modules.platform import outbox
from app.modules.platform.audit import SYSTEM
from app.worker.handlers import Deps
from app.worker.runner import run_event


@pytest.fixture
def enquiry(db: Session) -> Enquiry:
    templates.ensure_defaults(db, SYSTEM)
    e = create_enquiry(
        db,
        EnquiryInput(
            EnquiryType.BRIDE,
            "Noelani Kahale",
            "Noelani@Example.com",
            wedding_date=date(2027, 5, 1),
            region="HI",
        ),
        SYSTEM,
        today=date(2026, 12, 1),
    )
    db.flush()
    return e


def work(db: Session, mailer: RecordingMailer) -> list[str]:
    deps = Deps(settings=Settings(allowed_email="jessica@jstyle.example"), mailer=mailer)
    return [run_event(db, ev.id, deps) for ev in outbox.claim_due(db)]


def send_ack(db: Session, e: Enquiry, mailer: RecordingMailer) -> EmailMessage:
    outbox.enqueue(
        db, "email.send", f"ack:{e.id}", {"enquiry_id": str(e.id), "template": "enquiry_ack"}
    )
    assert work(db, mailer) == ["done"]
    msg = db.scalar(select(EmailMessage).where(EmailMessage.direction == "outbound"))
    assert msg is not None
    return msg


def inbound(**kw: Any) -> InboundMail:
    base: dict[str, Any] = {
        "rfc_message_id": "<client-1@mail.example>",
        "from_addr": "Noelani <noelani@example.com>",
        "to_addrs": ["jessica@jstyle.example"],
        "subject": "Re: Thank you",
        "body_text": "Hi Jessica, can we add one more bridesmaid?",
    }
    return InboundMail(**(base | kw))


def test_reply_threads_by_message_id(db: Session, enquiry: Enquiry) -> None:
    out = send_ack(db, enquiry, RecordingMailer())
    r = ingest_inbound(db, inbound(from_addr="other@else.com", in_reply_to=out.rfc_message_id))
    assert r.status == "attached" and r.enquiry_id == enquiry.id
    thread = db.get(EmailThread, out.thread_id)
    assert thread is not None and thread.unread
    assert ingest_inbound(db, inbound()).status == "duplicate"


def test_new_message_from_known_client_starts_conversation(db: Session, enquiry: Enquiry) -> None:
    r = ingest_inbound(db, inbound(subject="Quick question"))
    assert r.status == "attached" and r.enquiry_id == enquiry.id


def test_unrelated_mail_is_ignored(db: Session, enquiry: Enquiry) -> None:
    r = ingest_inbound(db, inbound(from_addr="newsletter@shop.example", subject="Sale!"))
    assert r.status == "ignored"
    assert db.scalar(select(EmailMessage)) is None
    assert len(db.scalars(select(Enquiry)).all()) == 1


def test_inbound_html_is_sanitised(db: Session, enquiry: Enquiry) -> None:
    ingest_inbound(db, inbound(body_html='<p onclick="x()">Hi<script>alert(1)</script></p>'))
    msg = db.scalar(select(EmailMessage))
    assert msg is not None and msg.body_html == "<p>Hi</p>"


def test_inbox_list_reply_and_read(authed: TestClient, db: Session, enquiry: Enquiry) -> None:
    mailer = RecordingMailer()
    out = send_ack(db, enquiry, mailer)
    ingest_inbound(db, inbound(in_reply_to=out.rfc_message_id))
    db.flush()

    threads = authed.get("/api/threads").json()
    assert len(threads) == 1 and threads[0]["unread"] and threads[0]["last_direction"] == "inbound"
    assert threads[0]["client_name"] == "Noelani Kahale"
    assert authed.get("/api/threads/unread-count").json() == {"unread": 1}
    tid = threads[0]["id"]

    detail = authed.get(f"/api/threads/{tid}").json()
    assert [m["direction"] for m in detail["messages"]] == ["outbound", "inbound"]

    r = authed.post(f"/api/threads/{tid}/reply", json={"body": "Of course!\n\nJessica <3"})
    assert r.status_code == 202
    assert authed.get(f"/api/threads/{tid}").json()["replies_sending"] == 1
    assert work(db, mailer) == ["done"]
    sent = mailer.sent[-1]
    assert sent.subject.startswith("Re: ")
    assert sent.in_reply_to == "<client-1@mail.example>"
    assert "Jessica &lt;3" in sent.html and sent.to == ["noelani@example.com"]
    detail = authed.get(f"/api/threads/{tid}").json()
    assert [m["direction"] for m in detail["messages"]] == ["outbound", "inbound", "outbound"]
    assert detail["unread"] is False

    assert authed.post(f"/api/threads/{tid}/unread").status_code == 204
    assert authed.get("/api/threads?unread=true").json()[0]["id"] == tid


def test_simulated_reply_only_locally(authed: TestClient, db: Session, enquiry: Enquiry) -> None:
    send_ack(db, enquiry, RecordingMailer())
    r = authed.post(f"/api/dev/enquiries/{enquiry.id}/simulate-reply", json={"body": "Yes please"})
    assert r.status_code == 201 and r.json()["status"] == "attached"
    threads = authed.get(f"/api/threads?enquiry_id={enquiry.id}").json()
    assert len(threads) == 1 and threads[0]["snippet"] == "Yes please"
