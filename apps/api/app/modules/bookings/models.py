from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, Timestamps, UUIDPk


class BookingStatus(StrEnum):
    PENDING = "pending"  # quote accepted; contract and deposit outstanding
    BOOKED = "booked"
    CANCELLED = "cancelled"


class Booking(UUIDPk, Timestamps, Base):
    """Created when a quote is accepted. Becomes BOOKED only when the gate is clear."""

    __tablename__ = "bookings"

    enquiry_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("enquiries.id"), unique=True
    )
    quote_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("quotes.id"))
    status: Mapped[str] = mapped_column(String(20), default=BookingStatus.PENDING, index=True)
    accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted_via: Mapped[str] = mapped_column(String(20))  # reply | staff
    accepted_message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("email_messages.id")
    )
    total_cents: Mapped[int] = mapped_column(Integer)
    deposit_cents: Mapped[int] = mapped_column(Integer)
    balance_cents: Mapped[int] = mapped_column(Integer)
    stylists_required: Mapped[int | None] = mapped_column(Integer)
    # Filled by Phase 5 (Mark as signed) and Phase 6 (verified deposit).
    contract_signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deposit_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    booked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_reason: Mapped[str | None] = mapped_column(Text)
