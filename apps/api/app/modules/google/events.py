"""Tiny hook other modules call when a wedding or trial changes. Imports nothing heavy."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.google.models import GoogleConnection
from app.modules.platform import outbox


def calendar_changed(db: Session, enquiry_id: uuid.UUID) -> None:
    """Queue a calendar update. The handler reads the current state, so extra calls are harmless."""
    on = db.scalar(select(GoogleConnection.id).where(GoogleConnection.calendar_enabled.is_(True)))
    if on is None:
        return
    outbox.enqueue(
        db,
        "calendar.sync",
        f"calendar:{enquiry_id}:{uuid.uuid4()}",
        {"enquiry_id": str(enquiry_id)},
        aggregate_type="enquiry",
        aggregate_id=enquiry_id,
    )
