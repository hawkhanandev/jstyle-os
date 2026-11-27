"""Outbox worker: claims due events and runs their handlers, one transaction per event.

Run with `python -m app.worker`. Several workers can run at once; SKIP LOCKED keeps them apart.
"""

from __future__ import annotations

import logging
import time
import uuid

from sqlalchemy.orm import Session, sessionmaker

from app.modules.email.send import Skip
from app.modules.platform import outbox
from app.modules.platform.audit import SYSTEM, write_audit
from app.modules.platform.models import OutboxEvent, OutboxStatus
from app.worker.handlers import HANDLERS, Deps

log = logging.getLogger("jstyle.worker")


def run_event(db: Session, event_id: uuid.UUID, deps: Deps) -> str:
    event = db.get(OutboxEvent, event_id, with_for_update=True)
    if event is None or event.status != OutboxStatus.IN_PROGRESS:
        return "skipped"
    handler = HANDLERS.get(event.kind)
    try:
        if handler is None:
            raise outbox.PermanentError(f"no handler for {event.kind}")
        with db.begin_nested():
            handler(db, event, deps)
        outbox.mark_done(event)
        result = "done"
    except Skip as exc:
        outbox.mark_done(event)
        event.last_error = f"skipped: {exc}"
        result = "skipped"
    except Exception as exc:  # noqa: BLE001 - every failure is recorded on the event
        outbox.mark_error(event, exc)
        if event.status in (OutboxStatus.DEAD, OutboxStatus.FAILED):
            write_audit(
                db,
                SYSTEM,
                f"outbox.{event.status}",
                entity_type="outbox_event",
                entity_id=event.id,
                after={"error": event.last_error},
            )
        log.warning("event %s (%s) failed: %s", event.id, event.kind, exc)
        result = event.status
    db.commit()
    return result


def tick(factory: sessionmaker[Session], deps: Deps, batch: int = 10) -> int:
    with factory() as db:
        ids = [e.id for e in outbox.claim_due(db, limit=batch)]
        db.commit()
    for event_id in ids:
        with factory() as db:
            run_event(db, event_id, deps)
    return len(ids)


def run_forever(factory: sessionmaker[Session], deps: Deps, idle_sleep: float = 2.0) -> None:
    log.info("worker started")
    while True:
        try:
            if tick(factory, deps) == 0:
                time.sleep(idle_sleep)
        except Exception:  # noqa: BLE001 - keep the worker alive; next tick retries
            log.exception("worker tick failed")
            time.sleep(idle_sleep * 5)
