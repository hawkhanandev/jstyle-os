from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, Timestamps, UUIDPk


class Intent(StrEnum):
    ACCEPT = "accept"
    CHANGE_REQUEST = "change_request"
    DECLINE = "decline"
    QUESTION = "question"
    OTHER = "other"


class SuggestionStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    DISMISSED = "dismissed"


class ReplySuggestion(UUIDPk, Timestamps, Base):
    """A suggested reading of a client's reply. Nothing changes until staff confirm it."""

    __tablename__ = "reply_suggestions"

    enquiry_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("enquiries.id"), index=True
    )
    message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("email_messages.id"), unique=True
    )
    intent: Mapped[str] = mapped_column(String(20))
    confidence: Mapped[str] = mapped_column(String(10))  # high | medium | low
    matched: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(12), default=SuggestionStatus.PENDING, index=True)
    applied_intent: Mapped[str | None] = mapped_column(String(20))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
