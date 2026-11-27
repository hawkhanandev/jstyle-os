from __future__ import annotations

import time
from collections.abc import Iterator
from datetime import date, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.db import get_session
from app.main import app
from app.modules.enquiries.models import Enquiry
from app.modules.forms import spam
from app.modules.forms.models import FormSubmission
from app.modules.forms.verifiers import SkipMailCheck, get_mail_check, get_turnstile
from app.modules.platform.models import OutboxEvent

SECRET = "test-secret"


class FakeTurnstile:
    ok = True

    def verify(self, token: str | None, ip: str | None) -> bool:
        return self.ok


@pytest.fixture
def turnstile() -> FakeTurnstile:
    return FakeTurnstile()


@pytest.fixture
def public(db: Session, turnstile: FakeTurnstile) -> Iterator[TestClient]:
    settings = Settings(
        secret_key=SECRET,
        allowed_email="jessica@jstyle.example",
        public_base_url="http://testserver",
    )
    app.dependency_overrides[get_session] = lambda: db
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_turnstile] = lambda: turnstile
    app.dependency_overrides[get_mail_check] = lambda: SkipMailCheck()
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def bride(**kw: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "form_token": spam.issue_form_token(SECRET, now=time.time() - 60),
        "full_name": "Kailani Akana",
        "email": "kailani@example.com",
        "phone": "808-555-0101",
        "wedding_date": (date.today() + timedelta(days=200)).isoformat(),
        "region": "HI",
        "venue_name": "Kualoa Ranch",
        "venue_address": "Kaneohe HI 96744",
        "attendants_hair": 2,
        "attendants_makeup": 2,
        "notes": "So excited",
    }
    body.update(kw)
    return body


def statuses(db: Session) -> list[str]:
    return [
        s.status for s in db.scalars(select(FormSubmission).order_by(FormSubmission.created_at))
    ]


def test_clean_bride_creates_enquiry_and_ack(public: TestClient, db: Session) -> None:
    res = public.post("/api/public/enquiries/bride", json=bride())
    assert res.status_code == 200 and res.json()["ok"]
    e = db.scalars(select(Enquiry)).one()
    assert e.region == "HI" and e.attendant_hair_count == 2
    assert db.scalars(select(OutboxEvent.idempotency_key)).one() == f"enquiry_ack:{e.id}"
    assert statuses(db) == ["accepted"]


def test_planner_form(public: TestClient, db: Session) -> None:
    res = public.post(
        "/api/public/enquiries/planner",
        json={
            "form_token": spam.issue_form_token(SECRET, now=time.time() - 60),
            "company_name": "Aloha Events",
            "contact_name": "Leilani",
            "email": "l@aloha.example",
            "event_date": (date.today() + timedelta(days=100)).isoformat(),
            "region": "HI",
            "client_name": "Bride Name",
            "services_needed": "Hair and makeup for 7",
        },
    )
    assert res.status_code == 200
    assert db.scalars(select(Enquiry)).one().type == "planner"


@pytest.mark.parametrize(
    ("override", "reason"),
    [
        ({"website": "http://spam.example"}, "honeypot"),
        ({"form_token": None}, "missing_form_token"),
        ({"email": "x@mailinator.com"}, "disposable_email"),
    ],
)
def test_suspicious_is_held_without_enquiry_or_email(
    public: TestClient, db: Session, override: dict[str, Any], reason: str
) -> None:
    res = public.post("/api/public/enquiries/bride", json=bride(**override))
    assert res.status_code == 200  # same thank-you as a real submission
    sub = db.scalars(select(FormSubmission)).one()
    assert sub.status == "held" and reason in sub.spam_reasons
    assert db.scalars(select(Enquiry)).first() is None
    assert db.scalars(select(OutboxEvent)).first() is None


def test_too_fast_is_held(public: TestClient, db: Session) -> None:
    public.post(
        "/api/public/enquiries/bride",
        json=bride(form_token=spam.issue_form_token(SECRET, now=time.time())),
    )
    assert "too_fast" in db.scalars(select(FormSubmission)).one().spam_reasons


def test_turnstile_failure_is_rejected(
    public: TestClient, turnstile: FakeTurnstile, db: Session
) -> None:
    turnstile.ok = False
    res = public.post("/api/public/enquiries/bride", json=bride())
    assert res.status_code == 400
    assert statuses(db) == ["rejected"]


def test_rate_limit_per_email(public: TestClient, db: Session) -> None:
    for i in range(3):
        public.post(
            "/api/public/enquiries/bride",
            json=bride(wedding_date=(date.today() + timedelta(days=100 + i)).isoformat()),
        )
    res = public.post("/api/public/enquiries/bride", json=bride())
    assert res.status_code == 429


def test_duplicate_is_merged_as_note(public: TestClient, db: Session) -> None:
    public.post("/api/public/enquiries/bride", json=bride())
    public.post("/api/public/enquiries/bride", json=bride(notes="Adding a flower girl"))
    e = db.scalars(select(Enquiry)).one()
    assert "Adding a flower girl" in (e.notes or "")
    assert statuses(db) == ["accepted", "merged"]


def test_spam_review_approve_and_delete(
    public: TestClient, authed: TestClient, db: Session
) -> None:
    public.post("/api/public/enquiries/bride", json=bride(website="x"))
    public.post("/api/public/enquiries/bride", json=bride(email="b@mailinator.com"))
    held = authed.get("/api/form-submissions").json()
    assert len(held) == 2
    assert authed.get("/api/form-submissions/stats").json()["held_total"] == 2

    real = next(h for h in held if h["email"] == "kailani@example.com")
    approved = authed.post(f"/api/form-submissions/{real['id']}/approve")
    assert approved.status_code == 200 and approved.json()["status"] == "approved"
    assert db.scalars(select(Enquiry)).one().email == "kailani@example.com"
    assert len(db.scalars(select(OutboxEvent)).all()) == 1

    junk = next(h for h in held if h["email"] == "b@mailinator.com")
    assert authed.post(f"/api/form-submissions/{junk['id']}/delete").json()["status"] == "deleted"
    assert authed.post(f"/api/form-submissions/{junk['id']}/approve").status_code == 404


def test_form_config_issues_token(public: TestClient) -> None:
    cfg = public.get("/api/public/forms/config").json()
    assert spam.fill_seconds(SECRET, cfg["form_token"]) is not None
