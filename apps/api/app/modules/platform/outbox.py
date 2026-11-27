"""Transactional outbox.

Business code calls enqueue() inside its own transaction. A dispatcher claims due rows with
SELECT ... FOR UPDATE SKIP LOCKED and a worker performs the side effect, then reports back with
mark_done() or mark_error(). The worker lands in Phase 3; this module is the contract.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.db import utcnow
from app.modules.platform.models import OutboxEvent, OutboxStatus

# Delay before attempt n+1 after n failed attempts; after the list, every 6 hours.
BACKOFF = [timedelta(minutes=m) for m in (1, 5, 15, 60)]
LATE_BACKOFF = timedelta(hours=6)
MAX_ATTEMPTS = 8


class PermanentError(Exception):
    """The side effect can never succeed as-is (e.g. invalid address). No retry."""


def enqueue(
    session: Session,
    kind: str,
    idempotency_key: str,
    payload: dict[str, Any] | None = None,
    *,
    aggregate_type: str | None = None,
    aggregate_id: uuid.UUID | None = None,
    not_before: datetime | None = None,
) -> uuid.UUID | None:
    """Queue a side effect. Returns the new id, or None if the key already exists."""
    stmt = (
        insert(OutboxEvent)
        .values(
            id=uuid.uuid4(),
            kind=kind,
            idempotency_key=idempotency_key,
            payload=payload or {},
            status=OutboxStatus.PENDING,
            attempts=0,
            next_attempt_at=not_before or utcnow(),
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
        )
        .on_conflict_do_nothing(index_elements=["idempotency_key"])
        .returning(OutboxEvent.id)
    )
    return session.execute(stmt).scalar_one_or_none()


def claim_due(session: Session, limit: int = 20, now: datetime | None = None) -> list[OutboxEvent]:
    """Lock and mark due events in_progress. Concurrent dispatchers never get the same row."""
    now = now or utcnow()
    rows = list(
        session.scalars(
            select(OutboxEvent)
            .where(OutboxEvent.status == OutboxStatus.PENDING, OutboxEvent.next_attempt_at <= now)
            .order_by(OutboxEvent.next_attempt_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
    )
    for row in rows:
        row.status = OutboxStatus.IN_PROGRESS
        row.attempts += 1
    return rows


def mark_done(event: OutboxEvent, now: datetime | None = None) -> None:
    event.status = OutboxStatus.DONE
    event.completed_at = now or utcnow()
    event.last_error = None


def mark_error(event: OutboxEvent, error: Exception, now: datetime | None = None) -> None:
    now = now or utcnow()
    event.last_error = f"{type(error).__name__}: {error}"[:2000]
    if isinstance(error, PermanentError):
        event.status = OutboxStatus.FAILED
    elif event.attempts >= MAX_ATTEMPTS:
        event.status = OutboxStatus.DEAD
    else:
        idx = event.attempts - 1
        delay = BACKOFF[idx] if idx < len(BACKOFF) else LATE_BACKOFF
        event.status = OutboxStatus.PENDING
        event.next_attempt_at = now + delay


def retry(event: OutboxEvent, now: datetime | None = None) -> None:
    """Staff action from the failed-automations list. Caller writes the audit row."""
    event.status = OutboxStatus.PENDING
    event.next_attempt_at = now or utcnow()
