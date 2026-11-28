from __future__ import annotations

from datetime import date, timedelta
from email.message import EmailMessage as Mime
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.main import app
from app.modules.email.mailer import OutgoingMail, RecordingMailer
from app.modules.email.models import EmailMessage, EmailThread
from app.modules.google import crypto
from app.modules.google import service as google
from app.modules.google.client import SCOPES, Grant, HistoryExpired, HistoryPage, RawMessage
from app.modules.google.models import CalendarEvent, GoogleConnection
from app.modules.google.routes import get_google_api
from app.modules.platform import outbox
from app.worker.handlers import Deps
from app.worker.runner import run_event

from .test_operations import TODAY, book, make_enquiry

SETTINGS = Settings(secret_key="test-secret", allowed_email="jessica@jstyle.example")
TEST_BOX = "jstyle.test@gmail.com"


class FakeSession:
    def __init__(self, api: FakeApi) -> None:
        self.api = api

    def profile(self) -> tuple[str, str]:
        return TEST_BOX, str(self.api.history_id)

    def history(self, start_history_id: str) -> HistoryPage:
        if self.api.history_expired:
            raise HistoryExpired()
        ids = [mid for hid, mid in self.api.added if hid > int(start_history_id)]
        return HistoryPage(message_ids=ids, history_id=str(self.api.history_id))

    def recent_inbox_ids(self, newer_than_days: int) -> list[str]:
        return [mid for _, mid in self.api.added]

    def get_raw(self, message_id: str) -> RawMessage:
        return self.api.messages[message_id]

    def send_raw(self, raw: bytes, thread_id: str | None) -> tuple[str, str]:
        self.api.sent.append((raw, thread_id))
        return f"sent{len(self.api.sent)}", thread_id or f"thread-new{len(self.api.sent)}"

    def put_event(self, calendar_id: str, event_id: str, body: dict[str, Any]) -> None:
        self.api.events[event_id] = body

    def delete_event(self, calendar_id: str, event_id: str) -> None:
        self.api.events.pop(event_id, None)


class FakeApi:
    def __init__(self) -> None:
        self.history_id = 100
        self.added: list[tuple[int, str]] = []
        self.messages: dict[str, RawMessage] = {}
        self.sent: list[tuple[bytes, str | None]] = []
        self.events: dict[str, dict[str, Any]] = {}
        self.revoked: list[str] = []
        self.scopes = list(SCOPES)
        self.history_expired = False

    def authorization_url(
        self, *, state: str, code_challenge: str, redirect_uri: str, login_hint: str | None
    ) -> str:
        assert redirect_uri.endswith("/api/integrations/google/callback")
        return f"https://accounts.google.test/auth?state={state}"

    def exchange(self, *, code: str, code_verifier: str, redirect_uri: str) -> Grant:
        return Grant(email=TEST_BOX, refresh_token="refresh-123", scopes=self.scopes)

    def session(self, refresh_token: str) -> FakeSession:
        assert refresh_token == "refresh-123"
        return FakeSession(self)

    def revoke(self, refresh_token: str) -> None:
        self.revoked.append(refresh_token)

    def deliver(
        self, sender: str, subject: str, body: str, thread: str = "t1", **headers: str
    ) -> str:
        m = Mime()
        m["From"] = sender
        m["To"] = TEST_BOX
        m["Subject"] = subject
        m["Message-ID"] = f"<m{len(self.messages)}@client.example>"
        for k, v in headers.items():
            m[k.replace("_", "-")] = v
        m.set_content(body)
        self.history_id += 1
        mid = f"g{len(self.messages)}"
        self.messages[mid] = RawMessage(mid, thread, ["INBOX", "UNREAD"], m.as_bytes())
        self.added.append((self.history_id, mid))
        return mid


@pytest.fixture
def api(client: TestClient) -> FakeApi:
    fake = FakeApi()
    app.dependency_overrides[get_google_api] = lambda: fake
    return fake


def connect(authed: TestClient) -> None:
    start = authed.get("/api/integrations/google/start")
    assert start.status_code == 302, start.text
    state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
    res = authed.get("/api/integrations/google/callback", params={"code": "c", "state": state})
    assert res.headers["location"].endswith("/settings?google=connected#google")


def test_connect_stores_encrypted_token_with_sending_off(
    authed: TestClient, db: Session, api: FakeApi
) -> None:
    assert authed.get("/api/integrations/google").json()["connected"] is False
    connect(authed)
    conn = db.scalar(select(GoogleConnection))
    assert conn is not None and conn.email == TEST_BOX
    assert "refresh-123" not in conn.refresh_token_enc
    assert crypto.decrypt("test-secret", conn.refresh_token_enc) == "refresh-123"
    status = authed.get("/api/integrations/google").json()
    assert status["connected"] and not status["send_enabled"] and not status["calendar_enabled"]

    authed.post("/api/integrations/google/disconnect")
    assert db.scalar(select(GoogleConnection)) is None
    assert api.revoked == ["refresh-123"]


def test_missing_permissions_are_refused(authed: TestClient, db: Session, api: FakeApi) -> None:
    api.scopes = ["openid", "email"]
    start = authed.get("/api/integrations/google/start")
    state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
    res = authed.get("/api/integrations/google/callback", params={"code": "c", "state": state})
    assert "google=missing_permissions" in res.headers["location"]
    assert db.scalar(select(GoogleConnection)) is None


def test_bad_state_is_refused(authed: TestClient, db: Session, api: FakeApi) -> None:
    authed.get("/api/integrations/google/start")
    res = authed.get("/api/integrations/google/callback", params={"code": "c", "state": "forged"})
    assert "google=expired" in res.headers["location"]


def test_sync_keeps_client_mail_and_ignores_the_rest(
    authed: TestClient, db: Session, api: FakeApi
) -> None:
    e = make_enquiry(db, TODAY + timedelta(days=200))
    api.deliver("Kailani <kailani@example.com>", "Question", "Do you do airbrush?", thread="ta")
    connect(authed)

    # First run backfills recent mail: the client's message is kept, nothing else exists yet.
    r = authed.post("/api/integrations/google/sync").json()
    assert r["attached"] == 1
    api.deliver("Newsletter <news@shop.example>", "Sale", "50% off")
    api.deliver("Kailani <kailani@example.com>", "Re: Question", "Also, trial dates?", thread="ta")
    r = authed.post("/api/integrations/google/sync").json()
    assert r["attached"] == 1
    # A second run with nothing new adds nothing.
    assert authed.post("/api/integrations/google/sync").json()["attached"] == 0

    threads = db.scalars(select(EmailThread).where(EmailThread.enquiry_id == e.id)).all()
    assert len(threads) == 1 and threads[0].provider_thread_id == "ta"
    bodies = db.scalars(
        select(EmailMessage.body_text).where(EmailMessage.thread_id == threads[0].id)
    ).all()
    assert len(bodies) == 2
    assert authed.get("/api/threads/unread-count").json()["unread"] == 1


def test_expired_history_starts_over_without_duplicates(
    authed: TestClient, db: Session, api: FakeApi
) -> None:
    make_enquiry(db, TODAY + timedelta(days=200))
    api.deliver("kailani@example.com", "Hi", "Hello")
    connect(authed)
    authed.post("/api/integrations/google/sync")
    api.history_expired = True
    assert authed.post("/api/integrations/google/sync").json()["attached"] == 0


def test_mail_goes_through_gmail_only_once_sending_is_switched_on(
    authed: TestClient, db: Session, api: FakeApi
) -> None:
    connect(authed)
    fallback = RecordingMailer()
    factory: Any = lambda: _NoClose(db)  # noqa: E731
    mailer = google.RoutingMailer(factory, api, SETTINGS, fallback)
    mail = OutgoingMail(
        from_addr="Jstyle <jessica@jstyle.example>",
        to=["kailani@example.com"],
        subject="Your quote",
        html="<p>Hi</p>",
        text="Hi",
        message_id="<outbox-1@jstyle-os>",
        provider_thread_id="ta",
    )
    mailer.send(mail)
    assert len(fallback.sent) == 1 and api.sent == []

    authed.put("/api/integrations/google/options", json={"send_enabled": True})
    sent = mailer.send(mail)
    assert sent.provider_message_id == "sent1" and sent.provider_thread_id == "ta"
    raw, thread = api.sent[0]
    assert thread == "ta"
    assert b"From: Jstyle <jstyle.test@gmail.com>" in raw


class _NoClose:
    """Lets the routing mailer use the test's session inside a `with` block."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def __enter__(self) -> Session:
        return self.db

    def __exit__(self, *exc: object) -> None:
        return None


def run_calendar(db: Session, api: FakeApi) -> list[str]:
    deps = Deps(settings=SETTINGS, mailer=RecordingMailer(), google=api)
    return [
        run_event(db, ev.id, deps)
        for ev in outbox.claim_due(db, limit=50)
        if ev.kind == "calendar.sync"
    ]


def test_calendar_follows_the_wedding(authed: TestClient, db: Session, api: FakeApi) -> None:
    connect(authed)
    e = make_enquiry(db, TODAY + timedelta(days=60))
    book(authed, db, e)
    # Switching calendar sync on adds the weddings already booked.
    authed.put("/api/integrations/google/options", json={"calendar_enabled": True})
    run_calendar(db, api)
    (event,) = api.events.values()
    assert event["summary"] == "Wedding: Kailani Akana"
    assert event["start"] == {"date": e.wedding_date.isoformat()}  # type: ignore[union-attr]

    new_day: date = TODAY + timedelta(days=90)
    authed.patch(f"/api/enquiries/{e.id}", json={"wedding_date": new_day.isoformat()})
    run_calendar(db, api)
    (event,) = api.events.values()
    assert event["start"] == {"date": new_day.isoformat()}

    authed.post(f"/api/enquiries/{e.id}/cancel-wedding", json={"reason": "Postponed"})
    run_calendar(db, api)
    assert api.events == {}
    row = db.scalar(select(CalendarEvent).where(CalendarEvent.enquiry_id == e.id))
    assert row is not None and row.deleted


def test_calendar_off_does_nothing(authed: TestClient, db: Session, api: FakeApi) -> None:
    connect(authed)
    e = make_enquiry(db, TODAY + timedelta(days=60))
    book(authed, db, e)
    assert set(run_calendar(db, api)) <= {"skipped"}
    assert api.events == {}
