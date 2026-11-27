from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, Timestamps, UUIDPk


class ScheduledStatus(StrEnum):
    SCHEDULED = "scheduled"
    QUEUED = "queued"  # handed to the outbox for sending
    SKIPPED = "skipped"  # no longer applied when it came due
    CANCELLED = "cancelled"


class ScheduledEmail(UUIDPk, Timestamps, Base):
    """An email due at a local time. Re-checked when it comes due, never sent blindly."""

    __tablename__ = "scheduled_emails"

    enquiry_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("enquiries.id"), index=True
    )
    kind: Mapped[str] = mapped_column(String(30))
    template_key: Mapped[str] = mapped_column(String(50))
    send_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(12), default=ScheduledStatus.SCHEDULED, index=True)
    ref_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))  # e.g. the quote
    outbox_event_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    note: Mapped[str | None] = mapped_column(Text)
