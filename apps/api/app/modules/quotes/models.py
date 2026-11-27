from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, Timestamps, UUIDPk


class QuoteStatus(StrEnum):
    DRAFT = "draft"
    AWAITING_APPROVAL = "awaiting_approval"
    SENDING = "sending"  # approved, email queued
    SEND_FAILED = "send_failed"  # approved, email failed; retry or withdraw
    SENT = "sent"
    ACCEPTED = "accepted"
    SUPERSEDED = "superseded"
    WITHDRAWN = "withdrawn"


class Quote(UUIDPk, Timestamps, Base):
    """A priced, versioned offer. Once submitted its numbers never change."""

    __tablename__ = "quotes"
    __table_args__ = (UniqueConstraint("enquiry_id", "version"),)

    enquiry_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("enquiries.id"), index=True
    )
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default=QuoteStatus.DRAFT, index=True)
    supersedes_quote_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quotes.id")
    )
    rate_card_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("rate_cards.id"))
    rate_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB)
    inputs: Mapped[dict[str, Any]] = mapped_column(JSONB)
    price_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB)
    subtotal_cents: Mapped[int] = mapped_column(Integer)
    minimum_adjustment_cents: Mapped[int] = mapped_column(Integer)
    total_cents: Mapped[int] = mapped_column(Integer)
    deposit_cents: Mapped[int] = mapped_column(Integer)
    balance_cents: Mapped[int] = mapped_column(Integer)
    stylists_required: Mapped[int | None] = mapped_column(Integer)
    review_flags: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    acknowledged_flags: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    note_to_client: Mapped[str | None] = mapped_column(Text)

    email_subject: Mapped[str | None] = mapped_column(String(300))
    email_body_html: Mapped[str | None] = mapped_column(Text)  # exact content sent
    email_body_text: Mapped[str | None] = mapped_column(Text)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    send_error: Mapped[str | None] = mapped_column(Text)
    outbox_event_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    email_message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("email_messages.id")
    )
    rejection_note: Mapped[str | None] = mapped_column(Text)
    withdrawn_reason: Mapped[str | None] = mapped_column(Text)


class QuoteLineItem(UUIDPk, Base):
    __tablename__ = "quote_line_items"

    quote_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quotes.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(30))
    description: Mapped[str] = mapped_column(String(200))
    quantity: Mapped[int] = mapped_column(Integer)
    unit_cents: Mapped[int] = mapped_column(Integer)
    amount_cents: Mapped[int] = mapped_column(Integer)
    sort: Mapped[int] = mapped_column(Integer)
