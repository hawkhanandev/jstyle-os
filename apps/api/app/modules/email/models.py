from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, Timestamps, UUIDPk


class EmailTemplate(UUIDPk, Timestamps, Base):
    """Versioned like rate cards: editing saves a new version; old ones are kept."""

    __tablename__ = "email_templates"
    __table_args__ = (UniqueConstraint("key", "version"),)

    key: Mapped[str] = mapped_column(String(50), index=True)
    version: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(100))
    subject: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text)  # Jinja, rendered to HTML
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)


class EmailThread(UUIDPk, Timestamps, Base):
    __tablename__ = "email_threads"

    provider_thread_id: Mapped[str | None] = mapped_column(String(200), unique=True)
    enquiry_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("enquiries.id"), index=True
    )
    subject: Mapped[str] = mapped_column(String(300))
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    unread: Mapped[bool] = mapped_column(Boolean, default=False)


class EmailMessage(UUIDPk, Timestamps, Base):
    __tablename__ = "email_messages"

    thread_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("email_threads.id"), index=True
    )
    provider_message_id: Mapped[str | None] = mapped_column(String(200), unique=True)
    rfc_message_id: Mapped[str] = mapped_column(String(300), unique=True)
    direction: Mapped[str] = mapped_column(String(10))  # outbound | inbound
    from_addr: Mapped[str] = mapped_column(String(320))
    to_addrs: Mapped[list[str]] = mapped_column(ARRAY(String))
    subject: Mapped[str] = mapped_column(String(300))
    body_html: Mapped[str | None] = mapped_column(Text)
    body_text: Mapped[str | None] = mapped_column(Text)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    template_key: Mapped[str | None] = mapped_column(String(50))
    outbox_event_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
