from __future__ import annotations

from collections.abc import Iterator
from datetime import date
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
from app.worker.handlers import Deps
from app.worker.runner import run_event

TODAY = date.today().isoformat()


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


def contract_sent(authed: TestClient, db: Session, e: Enquiry) -> dict[str, Any]:
    q = authed.post(f"/api/enquiries/{e.id}/quotes", json={"stylists_required": 1}).json()
    authed.post(f"/api/quotes/{q['id']}/submit", json={"acknowledged_flags": q["review_flags"]})
    authed.post(f"/api/quotes/{q['id']}/approve")
    work(db)
    authed.post(f"/api/quotes/{q['id']}/accept")
    authed.post(f"/api/enquiries/{e.id}/contract/prepare")
    authed.post(f"/api/enquiries/{e.id}/contract/send")
    assert work(db) == ["done"]
    return authed.get(f"/api/enquiries/{e.id}/paperwork").json()


def pay(authed: TestClient, e: Enquiry, amount: int, **kw: Any) -> dict[str, Any]:
    body = {"method": "venmo", "amount_cents": amount, "received_on": TODAY} | kw
    r = authed.post(f"/api/enquiries/{e.id}/payments", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def sign(authed: TestClient, contract_id: str) -> None:
    r = authed.post(
        f"/api/contracts/{contract_id}/mark-signed", data={"signed_on": TODAY, "method": "pdf"}
    )
    assert r.status_code == 200


def test_booked_only_with_signed_contract_and_verified_deposit(
    authed: TestClient, db: Session, enquiry: Enquiry
) -> None:
    paper = contract_sent(authed, db, enquiry)
    res = pay(authed, enquiry, 10000, reference="Venmo 1234")
    assert res["summary"]["awaiting_verification_cents"] == 10000
    assert res["summary"]["paid_cents"] == 0
    db.refresh(enquiry)
    assert enquiry.pipeline_status == "CONTRACT_DEPOSIT_PENDING"  # recorded isn't verified

    pid = res["payments"][0]["id"]
    assert authed.post(f"/api/payments/{pid}/verify").json()["status"] == "verified"
    inv = authed.get(f"/api/enquiries/{enquiry.id}/paperwork").json()["invoices"][0]
    assert inv["status"] == "paid"
    db.refresh(enquiry)
    assert enquiry.pipeline_status == "CONTRACT_DEPOSIT_PENDING"  # contract not signed yet

    mailer = RecordingMailer()
    sign(authed, paper["contracts"][0]["id"])
    db.refresh(enquiry)
    assert enquiry.pipeline_status == "BOOKED"
    assert work(db, mailer) == ["done"]
    assert mailer.sent[0].subject.startswith("You're booked!")
    s = authed.get(f"/api/enquiries/{enquiry.id}/payments").json()["summary"]
    assert s == {
        "total_cents": 90000,
        "paid_cents": 10000,
        "awaiting_verification_cents": 0,
        "outstanding_cents": 80000,
    }


def test_partial_and_rejected_payments(authed: TestClient, db: Session, enquiry: Enquiry) -> None:
    paper = contract_sent(authed, db, enquiry)
    sign(authed, paper["contracts"][0]["id"])
    a = pay(authed, enquiry, 5000, verify=True)["payments"][0]
    db.refresh(enquiry)
    assert enquiry.pipeline_status == "CONTRACT_DEPOSIT_PENDING"
    b = pay(authed, enquiry, 5000, method="zelle")["payments"][0]
    r = authed.post(f"/api/payments/{b['id']}/reject", json={})
    assert r.json()["detail"]["code"] == "reason_required"
    authed.post(f"/api/payments/{b['id']}/reject", json={"reason": "Not in Zelle"})
    db.refresh(enquiry)
    assert enquiry.pipeline_status == "CONTRACT_DEPOSIT_PENDING"
    pay(authed, enquiry, 5000, verify=True)
    db.refresh(enquiry)
    assert enquiry.pipeline_status == "BOOKED"

    # Voiding a verified payment after booking never un-books; it raises a task.
    authed.post(f"/api/payments/{a['id']}/void", json={"reason": "Duplicate entry"})
    db.refresh(enquiry)
    assert enquiry.pipeline_status == "BOOKED"
    task = db.scalar(select(Task).where(Task.kind == "deposit_reversed"))
    assert task is not None and task.entity_id == enquiry.id


def test_payment_validation(authed: TestClient, db: Session, enquiry: Enquiry) -> None:
    contract_sent(authed, db, enquiry)
    r = authed.post(
        f"/api/enquiries/{enquiry.id}/payments",
        json={"method": "venmo", "amount_cents": 100, "received_on": "2099-01-01"},
    )
    assert r.status_code == 409 and r.json()["detail"]["code"] == "future_date"
    r = authed.post(
        f"/api/enquiries/{enquiry.id}/payments",
        json={"method": "bitcoin", "amount_cents": 100, "received_on": TODAY},
    )
    assert r.status_code == 422
    p = pay(authed, enquiry, 100)["payments"][0]
    assert authed.post(f"/api/payments/{p['id']}/reopen").status_code == 409
    assert len(authed.get("/api/payments?status=recorded").json()) == 1
