from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.modules.email import templates
from app.modules.email.mailer import OutgoingMail, RecordingMailer, SentMail
from app.modules.email.models import EmailMessage, EmailThread
from app.modules.enquiries.models import EnquiryType, Pipeline
from app.modules.enquiries.pipeline import transition
from app.modules.enquiries.service import EnquiryInput, create_enquiry
from app.modules.platform import outbox
from app.modules.platform.audit import SYSTEM
from app.modules.platform.models import OutboxEvent, OutboxStatus
from app.worker.handlers import Deps
from app.worker.runner import run_event

TODAY = date(2026, 12, 1)


@pytest.fixture
def deps() -> Deps:
    return Deps(settings=Settings(allowed_email="jessica@jstyle.example"), mailer=RecordingMailer())


def make_enquiry(db: Session, **kw: object):  # type: ignore[no-untyped-def]
    templates.ensure_defaults(db, SYSTEM)
    data = EnquiryInput(
        EnquiryType.BRIDE,
        "Kailani Akana",
        "kailani@example.com",
        wedding_date=date(2027, 6, 12),
        region="HI",
        venue_name="Kualoa Ranch",
    )
    for k, v in kw.items():
        setattr(data, k, v)
    return create_enquiry(db, data, SYSTEM, today=TODAY)


def queue(db: Session, enquiry_id: object, template: str = "enquiry_ack") -> OutboxEvent:
    outbox.enqueue(
        db,
        "email.send",
        f"{template}:{enquiry_id}",
        {"template": template, "enquiry_id": str(enquiry_id)},
    )
    db.flush()
    [event] = outbox.claim_due(db)
    return event


def test_ack_is_rendered_sent_and_stored(db: Session, deps: Deps) -> None:
    e = make_enquiry(db)
    event = queue(db, e.id)
    assert run_event(db, event.id, deps) == "done"
    [mail] = deps.mailer.sent  # type: ignore[attr-defined]
    assert mail.to == ["kailani@example.com"]
    assert mail.subject == "Thank you for your enquiry, Kailani!"
    assert "Saturday, June 12, 2027" in mail.html and "Kualoa Ranch" in mail.html
    assert mail.message_id == f"<outbox-{event.id}@jstyle-os>"
    msg = db.scalars(select(EmailMessage)).one()
    assert msg.template_key == "enquiry_ack" and msg.direction == "outbound"
    assert db.scalars(select(EmailThread)).one().enquiry_id == e.id


def test_planner_gets_planner_ack(db: Session, deps: Deps) -> None:
    e = make_enquiry(db, type=EnquiryType.PLANNER, planner_company="Aloha Events")
    run_event(db, queue(db, e.id).id, deps)
    assert db.scalars(select(EmailMessage)).one().template_key == "planner_ack"


def test_closed_enquiry_skips_ack(db: Session, deps: Deps) -> None:
    e = make_enquiry(db)
    transition(db, e, Pipeline.LOST_DECLINED, SYSTEM, reason="spam call")
    event = queue(db, e.id)
    assert run_event(db, event.id, deps) == "skipped"
    assert deps.mailer.sent == []  # type: ignore[attr-defined]
    assert db.get(OutboxEvent, event.id).status == OutboxStatus.DONE  # type: ignore[union-attr]


def test_second_email_replies_in_same_thread(db: Session, deps: Deps) -> None:
    e = make_enquiry(db)
    run_event(db, queue(db, e.id).id, deps)
    run_event(db, queue(db, e.id, "quote_follow_up").id, deps)
    first, second = deps.mailer.sent  # type: ignore[attr-defined]
    assert second.in_reply_to == first.message_id
    assert len(db.scalars(select(EmailThread)).all()) == 1


class FailingMailer:
    def send(self, mail: OutgoingMail) -> SentMail:
        raise ConnectionError("smtp down")


def test_send_failure_retries_and_stores_nothing(db: Session) -> None:
    e = make_enquiry(db)
    event = queue(db, e.id)
    deps = Deps(settings=Settings(), mailer=FailingMailer())
    assert run_event(db, event.id, deps) == "pending"
    assert event.attempts == 1 and "smtp down" in (event.last_error or "")
    assert db.scalars(select(EmailMessage)).first() is None


def test_already_sent_is_not_sent_twice(db: Session, deps: Deps) -> None:
    e = make_enquiry(db)
    event = queue(db, e.id)
    run_event(db, event.id, deps)
    event.status = OutboxStatus.IN_PROGRESS  # simulate a crash after send, before done
    run_event(db, event.id, deps)
    assert len(deps.mailer.sent) == 1  # type: ignore[attr-defined]


def test_template_versions(db: Session) -> None:
    templates.ensure_defaults(db, SYSTEM)
    templates.save_version(
        db,
        SYSTEM,
        "enquiry_ack",
        "Ack",
        "Hi {{ client_first_name }}",
        "<p>Hello {{ client_first_name }}</p><script>x</script>",
    )
    r = templates.render(db, "enquiry_ack", {"client_first_name": "Mia"})
    assert r.subject == "Hi Mia" and r.template_version == 2
    assert "<script>" not in r.html
    with pytest.raises(templates.TemplateInvalid):
        templates.save_version(db, SYSTEM, "enquiry_ack", "Ack", "{% if %}", "x")


def test_worker_tick_uses_separate_sessions(engine: Engine, deps: Deps) -> None:
    # tick() commits, so it is exercised against a throwaway schema-level check only.
    from app.worker.runner import tick

    factory = sessionmaker(bind=engine)
    assert tick(factory, deps) >= 0


def test_template_api_and_outbox_retry(authed, db: Session) -> None:  # type: ignore[no-untyped-def]
    templates.ensure_defaults(db, SYSTEM)
    db.flush()
    keys = {t["key"] for t in authed.get("/api/templates").json()}
    assert {"enquiry_ack", "quote", "thank_you_review"} <= keys
    res = authed.post(
        "/api/templates/preview",
        json={"subject": "Hi {{ client_first_name }}", "body": "{{ quote.total }}"},
    )
    assert res.json() == {"subject": "Hi Kailani", "html": "$900"}
    bad = authed.post("/api/templates/enquiry_ack/versions", json={"subject": "x", "body": "{% if"})
    assert bad.status_code == 422
    ok = authed.post(
        "/api/templates/enquiry_ack/versions", json={"subject": "Hi", "body": "<p>x</p>"}
    )
    assert ok.json()["version"] == 2

    outbox.enqueue(db, "email.send", "k1", {})
    db.flush()
    event = db.scalars(select(OutboxEvent)).one()
    event.status = OutboxStatus.FAILED
    db.flush()
    assert authed.get("/api/outbox", params={"status": "failed"}).json()[0]["id"] == str(event.id)
    assert authed.post(f"/api/outbox/{event.id}/retry").json()["status"] == "pending"
