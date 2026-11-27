from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.db import get_session, utcnow
from app.main import app
from app.modules.platform import outbox
from app.modules.platform.audit import SYSTEM, Actor, write_audit
from app.modules.platform.models import AuditLog, OutboxEvent, OutboxStatus


def test_health_reports_database(db: Session) -> None:
    app.dependency_overrides[get_session] = lambda: db
    try:
        res = TestClient(app).get("/api/health")
    finally:
        app.dependency_overrides.clear()
    assert res.status_code == 200
    assert res.json()["database"] == "ok"


def test_audit_rows_are_append_only(db: Session) -> None:
    row = write_audit(
        db, Actor(account_email="owner@example.com", device_label="MacBook"), "auth.login"
    )
    db.flush()
    with pytest.raises(DBAPIError, match="append-only"), db.begin_nested():
        db.execute(text("UPDATE audit_logs SET action = 'x' WHERE id = :id"), {"id": row.id})
    with pytest.raises(DBAPIError, match="append-only"), db.begin_nested():
        db.execute(text("DELETE FROM audit_logs WHERE id = :id"), {"id": row.id})
    assert db.scalar(select(AuditLog.action).where(AuditLog.id == row.id)) == "auth.login"


def test_enqueue_is_idempotent(db: Session) -> None:
    first = outbox.enqueue(db, "email.send", "ack:123", {"to": "a@example.com"})
    second = outbox.enqueue(db, "email.send", "ack:123", {"to": "a@example.com"})
    assert first is not None
    assert second is None
    count = db.scalar(
        select(text("count(*)"))
        .select_from(OutboxEvent)
        .where(OutboxEvent.idempotency_key == "ack:123")
    )
    assert count == 1


def test_claim_skips_future_rows(db: Session) -> None:
    now = utcnow()
    outbox.enqueue(db, "email.send", "due:1")
    outbox.enqueue(db, "email.send", "later:1", not_before=now + timedelta(hours=1))
    db.flush()
    claimed = outbox.claim_due(db, now=now + timedelta(seconds=1))
    keys = {e.idempotency_key for e in claimed}
    assert "due:1" in keys and "later:1" not in keys
    assert all(e.status == OutboxStatus.IN_PROGRESS and e.attempts == 1 for e in claimed)


def test_backoff_then_dead(db: Session) -> None:
    outbox.enqueue(db, "email.send", "flaky:1")
    db.flush()
    event = db.scalars(select(OutboxEvent).where(OutboxEvent.idempotency_key == "flaky:1")).one()
    now = utcnow()
    event.attempts = 1
    outbox.mark_error(event, RuntimeError("timeout"), now=now)
    assert event.status == OutboxStatus.PENDING
    assert event.next_attempt_at == now + timedelta(minutes=1)
    event.attempts = outbox.MAX_ATTEMPTS
    outbox.mark_error(event, RuntimeError("timeout"), now=now)
    assert event.status == OutboxStatus.DEAD


def test_permanent_error_fails_without_retry(db: Session) -> None:
    outbox.enqueue(db, "email.send", "bad:1")
    db.flush()
    event = db.scalars(select(OutboxEvent).where(OutboxEvent.idempotency_key == "bad:1")).one()
    event.attempts = 1
    outbox.mark_error(event, outbox.PermanentError("invalid address"))
    assert event.status == OutboxStatus.FAILED
    outbox.retry(event)
    assert event.status == OutboxStatus.PENDING


def test_system_actor_has_no_person(db: Session) -> None:
    row = write_audit(db, SYSTEM, "outbox.dead")
    assert row.account_email is None and row.device_label == "system"
