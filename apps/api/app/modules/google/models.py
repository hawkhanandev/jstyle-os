from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, Timestamps, UUIDPk


class GoogleConnection(UUIDPk, Timestamps, Base):
    """The one Google account the CRM reads mail from, sends as and writes calendar events to.

    The refresh token is encrypted with a key derived from JSTYLE_SECRET_KEY.
    """

    __tablename__ = "google_connections"

    email: Mapped[str] = mapped_column(String(320))
    refresh_token_enc: Mapped[str] = mapped_column(Text)
    scopes: Mapped[str] = mapped_column(Text)
    connected_by: Mapped[str] = mapped_column(String(320))
    # Off until someone switches it on: connecting alone never sends mail as this account.
    send_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    calendar_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    calendar_id: Mapped[str] = mapped_column(String(200), default="primary")
    gmail_history_id: Mapped[str | None] = mapped_column(String(40))
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)


class CalendarEvent(UUIDPk, Timestamps, Base):
    """A Google Calendar event the CRM owns, so it can update or remove it later."""

    __tablename__ = "calendar_events"

    enquiry_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("enquiries.id"), index=True
    )
    kind: Mapped[str] = mapped_column(String(20))  # wedding | trial
    ref_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))  # the trial
    google_event_id: Mapped[str] = mapped_column(String(100), unique=True)
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)
