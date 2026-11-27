from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from email import message_from_bytes
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.modules.bookings.models import Booking
from app.modules.documents import service as documents
from app.modules.documents.storage import LocalStorage, set_storage
from app.modules.email import templates
from app.modules.email.mailer import RecordingMailer, to_mime
from app.modules.enquiries.models import Enquiry, EnquiryType, Pipeline
from app.modules.enquiries.pipeline import transition
from app.modules.enquiries.service import EnquiryInput, create_enquiry
from app.modules.platform import outbox
from app.modules.platform.audit import SYSTEM
from app.modules.pricing.service import ensure_defaults
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
            venue_name="Kualoa Ranch",
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


def accepted(authed: TestClient, db: Session, e: Enquiry) -> dict[str, Any]:
    q = authed.post(f"/api/enquiries/{e.id}/quotes", json={"stylists_required": 1}).json()
    authed.post(f"/api/quotes/{q['id']}/submit", json={"acknowledged_flags": q["review_flags"]})
    authed.post(f"/api/quotes/{q['id']}/approve")
    assert work(db) == ["done"]
    return authed.post(f"/api/quotes/{q['id']}/accept").json()


def test_invoice_numbers_are_yearly_and_sequential(db: Session) -> None:
    assert documents.next_invoice_number(db, 2026) == "JS-2026-0001"
    assert documents.next_invoice_number(db, 2026) == "JS-2026-0002"
    assert documents.next_invoice_number(db, 2027) == "JS-2027-0001"


def test_full_contract_flow_to_booked(authed: TestClient, db: Session, enquiry: Enquiry) -> None:
    accepted(authed, db, enquiry)
    p = authed.post(f"/api/enquiries/{enquiry.id}/contract/prepare").json()
    (contract,) = p["contracts"]
    (invoice,) = p["invoices"]
    assert contract["status"] == "prepared" and invoice["kind"] == "deposit"
    assert invoice["amount_cents"] == 10000 and invoice["number"].startswith("JS-")

    pdf = authed.get(f"/api/documents/{contract['document_id']}")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    assert pdf.headers["content-type"] == "application/pdf"

    # Preparing again replaces the unsent drafts.
    p = authed.post(f"/api/enquiries/{enquiry.id}/contract/prepare").json()
    assert [c["status"] for c in p["contracts"]] == ["prepared", "void"]
    assert [i["status"] for i in p["invoices"]] == ["prepared", "void"]

    assert authed.post(f"/api/enquiries/{enquiry.id}/contract/send").status_code == 202
    mailer = RecordingMailer()
    assert work(db, mailer) == ["done"]
    mail = mailer.sent[-1]
    assert mail.subject == "Your contract and deposit invoice"
    assert [a.content_type for a in mail.attachments] == ["application/pdf"] * 2
    assert "$100" in mail.html
    parsed = message_from_bytes(to_mime(mail).as_bytes())
    assert len([p for p in parsed.walk() if p.get_filename()]) == 2

    db.refresh(enquiry)
    assert enquiry.pipeline_status == "CONTRACT_DEPOSIT_PENDING"
    p = authed.get(f"/api/enquiries/{enquiry.id}/paperwork").json()
    assert p["contracts"][0]["status"] == "sent" and p["invoices"][0]["status"] == "issued"

    r = authed.post(
        f"/api/contracts/{p['contracts'][0]['id']}/mark-signed",
        data={"signed_on": date.today().isoformat(), "method": "pdf", "note": "By email"},
        files={"evidence": ("signed.pdf", b"%PDF-1.4 signed", "application/pdf")},
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "signed" and r.json()["signed_evidence_id"]
    b = authed.get(f"/api/enquiries/{enquiry.id}/booking").json()
    assert b["missing"] == ["deposit_verified"]

    # Deposit verification lands in Phase 6; the gate then books.
    booking = db.get(Booking, b["id"])
    assert booking is not None
    booking.deposit_verified_at = booking.contract_signed_at
    from app.modules.bookings.service import try_book

    assert try_book(db, booking, enquiry, SYSTEM) == []
    assert enquiry.pipeline_status == "BOOKED"


def test_cannot_prepare_before_acceptance(authed: TestClient, enquiry: Enquiry) -> None:
    r = authed.post(f"/api/enquiries/{enquiry.id}/contract/prepare")
    assert r.status_code == 404


def test_send_requires_prepare_and_evidence_type(
    authed: TestClient, db: Session, enquiry: Enquiry
) -> None:
    accepted(authed, db, enquiry)
    r = authed.post(f"/api/enquiries/{enquiry.id}/contract/send")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "not_prepared"
    p = authed.post(f"/api/enquiries/{enquiry.id}/contract/prepare").json()
    r = authed.post(
        f"/api/contracts/{p['contracts'][0]['id']}/mark-signed",
        data={"signed_on": "2026-12-03", "method": "paper"},
        files={"evidence": ("x.exe", b"MZ", "application/octet-stream")},
    )
    assert r.status_code == 422


def test_failed_send_returns_contract_to_prepared(
    authed: TestClient, db: Session, enquiry: Enquiry
) -> None:
    accepted(authed, db, enquiry)
    authed.post(f"/api/enquiries/{enquiry.id}/contract/prepare")
    authed.post(f"/api/enquiries/{enquiry.id}/contract/send")

    class Broken(RecordingMailer):
        def send(self, mail: Any) -> Any:
            from app.modules.platform.outbox import PermanentError

            raise PermanentError("mailbox full")

    assert work(db, Broken()) == ["failed"]
    p = authed.get(f"/api/enquiries/{enquiry.id}/paperwork").json()
    assert p["contracts"][0]["status"] == "prepared"
    db.refresh(enquiry)
    assert enquiry.pipeline_status == "QUOTE_ACCEPTED"


def test_settings_roundtrip_and_terms_sanitised(authed: TestClient) -> None:
    s = authed.get("/api/settings").json()
    assert s["scheduling"] == {"deposit_due_days": 7, "balance_due_hours": 48}
    assert "DRAFT TERMS" in s["contract_terms"]["bride"]
    r = authed.put(
        "/api/settings/contract-terms",
        json={"bride": "<p>Ok<script>x</script></p>", "planner": "<ol><li>One</li></ol>"},
    )
    assert r.json()["contract_terms"]["bride"] == "<p>Ok</p>"
    r = authed.put(
        "/api/settings/business",
        json={"name": "Jstyle", "legal_name": "Jstyle LLC", "address": "1 Main St\nHonolulu HI"},
    )
    assert r.json()["business"]["legal_name"] == "Jstyle LLC"
